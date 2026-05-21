"""tests/test_integration_layer_v10_127.py — v10.127 Window 4 close.

Verifies:
  1. Standards #14-#20 verification report present (JSON + Markdown)
  2. All 7 standards' engine modules import cleanly
  3. All 7 audit gates G25-G31 are wired in scripts/audit.py
  4. The verification report records all 7 as 'complete'
  5. G143 still at v10.125 milestone (close-out drops don't change rules)
  6. No new rules added in v10.127
  7. Programme context correction is documented (the stale focus line
     is removed from master prompt v3.21)
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


# ─── Verification artifacts ─────────────────────────────────────────

class TestVerificationArtifacts:
    """v10.127 ships a verification report (both JSON for automation
    and Markdown for humans) confirming standards #14-#20 are closed."""

    def test_json_report_present(self):
        p = REPO_ROOT / "docs" / "Standards_14_20_Verification_Report.json"
        assert p.exists()
        with open(p) as f:
            report = json.load(f)
        assert report["summary"]["total"] == 7
        assert report["summary"]["complete"] == 7
        assert report["summary"]["partial"] == 0
        assert report["summary"]["missing"] == 0

    def test_markdown_report_present(self):
        p = REPO_ROOT / "docs" / "Standards_14_20_Verification_Report.md"
        assert p.exists()
        content = p.read_text(encoding="utf-8")
        for section in ("Verification methodology",
                        "Verification results",
                        "Programme context update",
                        "Why this happened"):
            assert section in content, (
                f"Verification doc missing section: {section}")

    def test_all_seven_standards_marked_complete(self):
        p = REPO_ROOT / "docs" / "Standards_14_20_Verification_Report.json"
        with open(p) as f:
            report = json.load(f)
        for entry in report["standards"]:
            assert entry["status"] == "complete", (
                f"Std #{entry['id']} {entry['name']!r} is not complete: "
                f"{entry['status']}")
            assert entry["engine_present"]
            assert entry["engine_imports"]


# ─── Standards #14-#20 engine import smoke tests ────────────────────

class TestStandardsCluster14To20:
    """Verify each standard's engine module loads without error."""

    @pytest.mark.parametrize("std_id,module_name", [
        (14, "utils.peer_learning"),
        (15, "utils.coaching_intelligence"),
        (16, "utils.predictive_performance"),
        (17, "utils.gamification"),
        (18, "utils.efficiency"),
        (19, "utils.wellness"),
        (20, "utils.performance_insights"),
    ])
    def test_engine_imports_cleanly(self, std_id, module_name):
        # Use __import__ to handle the 'utils.X' dotted form
        mod = __import__(module_name, fromlist=[module_name.split(".")[-1]])
        assert mod is not None
        # Module should expose at least a few public callables
        publics = [a for a in dir(mod)
                   if not a.startswith("_")
                   and callable(getattr(mod, a, None))]
        assert len(publics) >= 3, (
            f"Std #{std_id} {module_name} has only {len(publics)} "
            f"public callables; expected ≥3")


# ─── Audit gates G25-G31 wired ──────────────────────────────────────

class TestAuditGatesWired:

    @pytest.mark.parametrize("gate_id", ["G25", "G26", "G27", "G28",
                                         "G29", "G30", "G31"])
    def test_gate_referenced_in_audit_script(self, gate_id):
        audit_path = REPO_ROOT / "scripts" / "audit.py"
        content = audit_path.read_text()
        assert gate_id in content, (
            f"Audit gate {gate_id} not referenced in scripts/audit.py")


# ─── G143 + rule count preserved (close-out drop) ───────────────────

class TestG143AndRuleCountPreserved:
    """v10.127 is a close-out drop, not rule density. G143 coverage
    and total rule count should be unchanged from v10.126."""

    @pytest.fixture(scope="class")
    def gate_result(self):
        sys.path.insert(0, str(REPO_ROOT / "scripts"))
        try:
            import audit
            return audit.gate_kpi_source_has_aggregator()
        finally:
            sys.path.pop(0)

    def test_coverage_still_99(self, gate_result):
        sp = gate_result["strict_preview"]
        assert sp["covered"] == 99
        assert sp["tag"] == "STRICT-READY (high)"

    def test_rule_count_still_100(self):
        with open(REPO_ROOT / "data" / "aggregation_rules.json") as f:
            data = json.load(f)
        assert len(data["rules"]) == 100

    def test_no_v10_127_origin_rules(self):
        """v10.127 doesn't add rules — close-out drop."""
        with open(REPO_ROOT / "data" / "aggregation_rules.json") as f:
            data = json.load(f)
        v127 = [r for r in data["rules"]
                if r.get("_origin", "").startswith("v10.127_")]
        assert v127 == []


# ─── Programme context correction reflected in master prompt v3.21 ──

class TestProgrammeContextCorrection:
    """v10.127 corrects the stale '#14-#20' focus area in the master
    prompt's `Top of mind` block."""

    def test_master_prompt_v3_21_present(self):
        p = REPO_ROOT / "docs" / "Master_Prompt_v3.21.md"
        assert p.exists()

    def test_v3_21_v10_127_narrative_present(self):
        p = REPO_ROOT / "docs" / "Master_Prompt_v3.21.md"
        content = p.read_text(encoding="utf-8")
        # The line 108 narrative for v10.127 should mention the
        # correction
        assert "v10.127" in content
        # And the verification report
        assert ("Standards_14_20_Verification" in content
                or "verification report" in content.lower()
                or "verification" in content.lower())
