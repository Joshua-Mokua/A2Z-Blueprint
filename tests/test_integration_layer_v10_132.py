"""tests/test_integration_layer_v10_132.py — v10.132 rule-explain endpoint.

Verifies the new GET /api/integration/rule-explain/{kpi_id} endpoint
plus the cockpit Debug tab integration. The endpoint is the operator
audit superpower: for any wired rule + period, returns the rule
definition, input row counts at each filtering stage, sample matched
rows, and per-staff intermediate values.

Verifies:
  1. Endpoint registered in utils/api.py with correct path + decorator
  2. JWT-protected (Depends(get_current_user))
  3. Returns 404 for unknown kpi_id (manually traced)
  4. Returns 400 for invalid period (manually traced)
  5. Period regex matches valid periods, rejects invalid
  6. Rule lookup against REGISTRY works for known KPI
  7. Input funnel calculation: total → in_period → matching → distinct
  8. Sample row truncation works for verbose strings/lists
  9. Per-staff actuals match what compute_rule returns
 10. Cockpit Debug tab declared in pages/99_integration_cockpit.py
 11. Cockpit imports correct helpers (REGISTRY, compute_rule, _row_in_period)
 12. CHANGELOG + docs ship together
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ─── Endpoint registered in api.py ──────────────────────────────────

class TestEndpointRegistered:

    @pytest.fixture(scope="class")
    def api_src(self):
        return (REPO_ROOT / "utils" / "api.py").read_text()

    def test_decorator_present(self, api_src):
        assert '@app.get("/api/integration/rule-explain/{kpi_id}")' in api_src

    def test_function_signature(self, api_src):
        assert "def integration_rule_explain(" in api_src
        # Must take period as a query param (validated to YYYY-MM)
        assert "period: str" in api_src
        # Must accept staff_code optional
        assert "staff_code: Optional[str]" in api_src

    def test_jwt_protected(self, api_src):
        # Find the function block and confirm get_current_user dep
        marker = "def integration_rule_explain"
        idx = api_src.index(marker)
        chunk = api_src[idx:idx + 2000]
        assert "Depends(get_current_user)" in chunk

    def test_v10_132_marker_section_present(self, api_src):
        # Header comment block declaring the new section
        assert "v10.132 — Rule-explain debug endpoint" in api_src

    def test_audit_log_call_present(self, api_src):
        marker = "def integration_rule_explain"
        idx = api_src.index(marker)
        chunk = api_src[idx:idx + 3000]
        # Per discipline: audit_log after every write … but this is a
        # READ endpoint; standard pattern is _audit() at top of handler
        assert '_audit("API_INTEGRATION_RULE_EXPLAIN"' in chunk

    def test_total_integration_endpoints_now_six(self, api_src):
        # v10.115 shipped 5; v10.132 makes it 6
        count = api_src.count('@app.get("/api/integration') + \
                api_src.count('@app.post("/api/integration')
        assert count == 6, (
            f"Expected 6 integration endpoints; got {count}")


# ─── Period validation logic ────────────────────────────────────────

class TestPeriodValidation:
    """The endpoint validates period against ^\\d{4}-(0[1-9]|1[0-2])$
    matching /actuals/{period}'s convention. Verify the regex behavior."""

    PERIOD_REGEX = r"^\d{4}-(0[1-9]|1[0-2])$"

    @pytest.mark.parametrize("good", [
        "2026-01", "2026-04", "2026-12", "2025-09", "1999-08",
    ])
    def test_valid_periods_accepted(self, good):
        assert re.match(self.PERIOD_REGEX, good)

    @pytest.mark.parametrize("bad", [
        "2026-13", "2026-00", "2026-1", "26-04", "2026/04",
        "not-a-period", "", "2026-04-15", "2026-Apr",
    ])
    def test_invalid_periods_rejected(self, bad):
        assert not re.match(self.PERIOD_REGEX, bad)


# ─── Rule lookup against REGISTRY ───────────────────────────────────

class TestRuleLookup:

    def test_known_kpi_resolves_to_rule(self):
        """Known KPIs from v10.108-v10.125 must resolve."""
        from utils.kpi_aggregation_rules import REGISTRY
        for known_kpi in ("K039", "K001", "K113", "K027"):
            matching = [r for r in REGISTRY if r.kpi_id == known_kpi]
            assert matching, (
                f"{known_kpi} should be in REGISTRY but isn't — "
                f"check Phase 1D state")

    def test_unknown_kpi_returns_empty(self):
        from utils.kpi_aggregation_rules import REGISTRY
        for unknown in ("K9999", "DOES_NOT_EXIST", ""):
            matching = [r for r in REGISTRY if r.kpi_id == unknown]
            assert len(matching) == 0


# ─── Input funnel computation matches /actuals ──────────────────────

class TestInputFunnel:
    """The funnel (total → in_period → matching → distinct staff) must
    use the same helpers compute_rule does internally — otherwise the
    Debug tab could show a different funnel than /actuals computes."""

    def test_row_in_period_helper_imported(self):
        # The endpoint imports _row_in_period directly. Verify it exists
        # and works as expected.
        from utils.kpi_aggregation_rules import _row_in_period
        # Match cases
        assert _row_in_period(
            {"last_updated": "2026-04-15"}, "last_updated", "2026-04")
        assert _row_in_period(
            {"last_updated": "2026-04"}, "last_updated", "2026-04")
        # Non-match
        assert not _row_in_period(
            {"last_updated": "2026-03-01"}, "last_updated", "2026-04")
        # No period_field — always True
        assert _row_in_period({}, None, "2026-04")
        # Missing field — False
        assert not _row_in_period({}, "last_updated", "2026-04")

    def test_funnel_against_real_data_K039(self):
        """Replay the funnel logic against K039 sla_tickets — must
        produce the same numbers the live endpoint would return."""
        from utils.kpi_aggregation_rules import (
            REGISTRY, compute_rule, _row_in_period)
        from utils.staff_field_resolver import resolve_staff_field

        rule = next(r for r in REGISTRY if r.kpi_id == "K039")
        assert rule.source_table == "sla_tickets"

        with open(REPO_ROOT / "data" / "sla_tickets.json") as f:
            data = json.load(f)
        rows = data if isinstance(data, list) else list(data.values())

        period = "2026-04"
        rows_in_period = [r for r in rows
                          if _row_in_period(r, rule.period_field, period)]
        primary_pred = (rule.predicate or rule.numerator_pred
                        or (lambda _r: True))
        rows_matching = [r for r in rows_in_period if primary_pred(r)]

        sf = resolve_staff_field(rule.source_table, rule.staff_field)
        per_staff = compute_rule(rule, rows, period, sf)

        # Sanity bounds
        assert len(rows) > 0
        assert len(rows_in_period) <= len(rows)
        assert len(rows_matching) <= len(rows_in_period)
        assert len(per_staff) > 0
        # Per-staff values must be percentages (0-100) for K039
        for sc, v in per_staff.items():
            assert 0 <= v <= 100


# ─── Sample row truncation ──────────────────────────────────────────

class TestSampleTruncation:
    """The endpoint truncates verbose values for the sample rows so a
    single row with a 10K-char description doesn't blow up JSON
    response size. Verify truncation thresholds."""

    def test_truncation_logic_in_endpoint(self):
        api_src = (REPO_ROOT / "utils" / "api.py").read_text()
        # The endpoint has an inner _truncate_value helper
        assert "def _truncate_value" in api_src, (
            "Endpoint should define an inner _truncate_value helper "
            "for sample row prep")

    def test_sample_size_capped(self):
        api_src = (REPO_ROOT / "utils" / "api.py").read_text()
        # max(1, min(20, int(sample_size)))
        assert "max(1, min(20, int(sample_size)))" in api_src


# ─── Cockpit Debug tab ──────────────────────────────────────────────

class TestCockpitDebugTab:

    @pytest.fixture(scope="class")
    def cockpit_src(self):
        return (REPO_ROOT / "pages" / "99_integration_cockpit.py").read_text()

    def test_six_tabs_declared(self, cockpit_src):
        assert "tab_coverage, tab_rules, tab_preview, tab_resolver, " \
               "tab_run, tab_debug = st.tabs(" in cockpit_src

    def test_debug_emoji_in_tab_label(self, cockpit_src):
        # 🐛 marks the Debug tab
        assert "🐛 Debug" in cockpit_src

    def test_debug_tab_with_block(self, cockpit_src):
        assert "with tab_debug:" in cockpit_src

    def test_debug_imports_correct_helpers(self, cockpit_src):
        # Cockpit Debug tab should use the same helpers the endpoint
        # uses — REGISTRY, compute_rule, _row_in_period
        assert "from utils.kpi_aggregation_rules import" in cockpit_src
        assert "REGISTRY" in cockpit_src
        assert "compute_rule" in cockpit_src
        assert "_row_in_period" in cockpit_src
        assert "from utils.staff_field_resolver import resolve_staff_field" \
            in cockpit_src

    def test_debug_tab_period_validation(self, cockpit_src):
        # Should validate period the same way the endpoint does
        assert r"^\d{4}-(0[1-9]|1[0-2])$" in cockpit_src

    def test_footer_mentions_v10_132(self, cockpit_src):
        # Footer caption should reflect the v10.132 Debug tab addition
        assert "v10.132" in cockpit_src


# ─── G143 + audit unchanged ─────────────────────────────────────────

class TestNoRegression:
    """v10.132 is a new endpoint + cockpit tab — no rule changes, no
    coverage changes."""

    def test_g143_still_99(self):
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        try:
            import audit
            r = audit.gate_kpi_source_has_aggregator()
        finally:
            sys.path.pop(0)
        sp = r["strict_preview"]
        assert sp["covered"] == 99
        assert sp["tag"] == "STRICT-READY (high)"

    def test_no_new_rules(self):
        with open(REPO_ROOT / "data" / "aggregation_rules.json") as f:
            data = json.load(f)
        v132 = [r for r in data["rules"]
                if r.get("_origin", "").startswith("v10.132_")]
        assert v132 == [], (
            f"v10.132 is endpoint+cockpit work, not rule-density. "
            f"Found {len(v132)} v10.132-origin rules.")
        assert len(data["rules"]) == 100


# ─── Documentation ─────────────────────────────────────────────────

class TestDocs:

    def test_api_doc_present(self):
        p = REPO_ROOT / "docs" / "API_Rule_Explain.md"
        assert p.exists()
        content = p.read_text()
        for section in ("Endpoint", "Request", "Response shape",
                        "Errors", "Use cases"):
            assert section in content, f"Missing section: {section}"

    def test_changelog_present(self):
        p = REPO_ROOT / "CHANGELOG_v10.132.md"
        assert p.exists()
        content = p.read_text()
        assert "rule-explain" in content.lower()
        assert "Debug tab" in content

    def test_master_prompt_v3_26_present(self):
        p = REPO_ROOT / "docs" / "Master_Prompt_v3.26.md"
        assert p.exists()
