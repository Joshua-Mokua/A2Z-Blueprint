"""tests/test_navigation_v10_153.py — Navigation Hotfix verification.

Verifies the v10.153 deliverable:
- All 9 cockpit pages on disk are referenced in app.py
- The 9 specific cockpits we wired (Strategy, Product, Risk, Credit
  Governance, Revenue Assurance, Finance, Trade Finance, ML Governance,
  Integration) each have at least one registration
- G149 gate function exists and passes
- G149 registered in GATES list
- No regression — existing G147/G148 still pass
- app.py still parses cleanly
"""
from __future__ import annotations
import ast
import importlib.util
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
APP_PATH = REPO_ROOT / "app.py"
AUDIT_PATH = REPO_ROOT / "scripts" / "audit.py"


def _load(name: str, path: Path):
    spec = importlib.util.spec_from_file_location(name, str(path))
    m = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = m
    spec.loader.exec_module(m)
    return m


class TestAppParses:
    def test_app_py_parses_after_edits(self):
        ast.parse(APP_PATH.read_text(encoding="utf-8"))


class TestCockpitsRegistered:
    EXPECTED_COCKPITS = [
        "15_strategy_arc_cockpit.py",
        "16_product_arc_cockpit.py",
        "93_risk_arc_cockpit.py",
        "94_credit_governance_cockpit.py",
        "95_revenue_assurance_cockpit.py",
        "96_finance_arc_cockpit.py",
        "97_trade_finance_arc_cockpit.py",
        "98_ml_governance_arc_cockpit.py",
        "99_integration_cockpit.py",
    ]

    def test_each_cockpit_referenced_in_app(self):
        text = APP_PATH.read_text(encoding="utf-8")
        for cockpit in self.EXPECTED_COCKPITS:
            ref = f"pages/{cockpit}"
            assert ref in text, (
                f"v10.153: {cockpit} not registered in app.py — "
                f"add a _pg() entry to the appropriate _xxx_grp")

    def test_strategy_arc_in_exec_grp(self):
        # Strategy belongs in executive nav. Verify the registration
        # is between _exec_grp's `_dg([` and the matching `])`
        text = APP_PATH.read_text(encoding="utf-8")
        start = text.find("_exec_grp = _dg([")
        assert start > -1
        end = text.find("\n])", start)
        assert end > -1
        section = text[start:end]
        assert "15_strategy_arc_cockpit.py" in section, (
            "Strategy Arc Cockpit should be registered in _exec_grp")

    def test_product_arc_in_retail_and_comm(self):
        # Product spans retail + commercial — both groups
        text = APP_PATH.read_text(encoding="utf-8")
        for grp in ("_retail_grp", "_comm_grp"):
            start = text.find(f"{grp} = _dg([")
            assert start > -1
            end = text.find("\n])", start)
            section = text[start:end]
            assert "16_product_arc_cockpit.py" in section, (
                f"Product Arc Cockpit should be registered in {grp}")


class TestG149Gate:
    def test_g149_function_exists(self):
        m = _load("audit_for_g149", AUDIT_PATH)
        assert hasattr(m, "gate_cockpits_registered_in_app")

    def test_g149_in_gates_list(self):
        m = _load("audit_g149_reg", AUDIT_PATH)
        gate_ids = [g[0] for g in m.GATES]
        assert "G149" in gate_ids

    def test_g149_passes(self):
        m = _load("audit_g149_pass", AUDIT_PATH)
        result = m.gate_cockpits_registered_in_app()
        assert result["passed"] is True, (
            f"G149 failed: {result.get('violations')}")
        assert result["n_cockpits_on_disk"] == 9
        assert result["n_cockpits_registered"] == 9

    def test_g149_returns_proper_shape(self):
        m = _load("audit_g149_shape", AUDIT_PATH)
        result = m.gate_cockpits_registered_in_app()
        for key in ("id", "name", "passed", "summary",
                    "violations", "n_cockpits_on_disk",
                    "n_cockpits_registered"):
            assert key in result
        assert result["id"] == "G149"
        assert result["name"] == "cockpits_registered_in_app"


class TestNoRegression:
    def test_g147_still_passes(self):
        m = _load("audit_g147_intact", AUDIT_PATH)
        result = m.gate_product_module_closed()
        assert result["passed"] is True

    def test_g148_still_passes(self):
        m = _load("audit_g148_intact", AUDIT_PATH)
        result = m.gate_product_arc_ui_integrated()
        assert result["passed"] is True

    def test_total_gate_count(self):
        m = _load("audit_count", AUDIT_PATH)
        # v10.151 was 148 gates; v10.153 adds G149 → 149
        assert len(m.GATES) == 149

    def test_existing_pages_still_referenced(self):
        # Make sure we didn't accidentally break any existing _pg() entries
        text = APP_PATH.read_text(encoding="utf-8")
        for existing in ("pages/0_home.py", "pages/1_perform.py",
                          "pages/5_products.py", "pages/7_admin.py",
                          "pages/25_treasury.py", "pages/81_alm.py"):
            assert existing in text, (
                f"existing page {existing} unexpectedly removed from app.py")
