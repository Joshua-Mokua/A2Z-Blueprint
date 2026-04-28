"""tests/test_audit_smoke.py — meta-test: scripts/audit.py runs cleanly.

This isn't a behavioral test of the codebase under audit — it's a
smoke test for the audit infrastructure itself. If the audit script
crashes (import error, regex bug, gate function raises), this catches
it before CI-on-every-push catches it.

Also verifies the JSON output is well-formed, since downstream tools
(badges, dashboards, slack notifications) parse it.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).parent.parent
AUDIT = ROOT / "scripts" / "audit.py"


@pytest.fixture(scope="module")
def audit_json() -> dict:
    """Run the audit script in JSON mode and return the parsed payload.
    Cached at module scope — running the audit is the slowest test in
    the suite and we don't want to pay for it 4 times."""
    result = subprocess.run(
        [sys.executable, str(AUDIT), "--json"],
        capture_output=True,
        text=True,
        cwd=str(ROOT),
        timeout=60,
    )
    assert result.returncode == 0, (
        f"Audit script crashed:\nstdout: {result.stdout}\nstderr: {result.stderr}"
    )
    try:
        return json.loads(result.stdout)
    except json.JSONDecodeError as e:
        pytest.fail(f"Audit JSON malformed: {e}\noutput: {result.stdout[:500]}")


class TestAuditScript:
    def test_runs_without_crashing(self, audit_json):
        assert audit_json is not None

    def test_passes_all_gates(self, audit_json):
        """The canonical tree must pass 12/12. If a test introduces a
        regression (e.g. a SQL string with raw concatenation), this fails
        loudly."""
        assert audit_json["passed"] == audit_json["total"], (
            f"Audit failed: {audit_json['passed']}/{audit_json['total']} gates"
        )

    def test_score_is_100_pct(self, audit_json):
        assert audit_json["score_pct"] == 100.0

    def test_has_fourteen_gates(self, audit_json):
        assert audit_json["total"] == 14

    def test_every_gate_has_required_fields(self, audit_json):
        for gate in audit_json["gates"]:
            assert "id" in gate
            assert "name" in gate
            assert "passed" in gate
            assert "summary" in gate
            assert isinstance(gate["passed"], bool)

    def test_g8_no_longer_vacuous(self, audit_json):
        """Post-v5.18, G8 must report a non-zero compliant submitter
        count. Vacuous-pass is the regression we built G8 to catch."""
        g8 = next(g for g in audit_json["gates"] if g["id"] == "G8")
        assert g8["passed"]
        assert "compliant submitter call(s)" in g8["summary"]
        # Must show at least 1 — we wired pilot modules in v5.18 + v5.19
        assert "0 compliant submitter" not in g8["summary"]

    def test_g8_no_bypass_writers(self, audit_json):
        g8 = next(g for g in audit_json["gates"] if g["id"] == "G8")
        assert "0 bypass writer(s)" in g8["summary"]

    def test_g14_reports_adoption(self, audit_json):
        """Post-v5.21, G14 must report the core-split adoption percentage.
        It must show at least one shim and at least one migrated page —
        otherwise the v5.21 work has regressed."""
        g14 = next(g for g in audit_json["gates"] if g["id"] == "G14")
        assert g14["passed"]
        assert "shim(s)" in g14["summary"]
        # Must have at least one adopted page
        assert "0/" not in g14["summary"].split("pages adopted")[0]


class TestAuditGateFunctions:
    """Direct unit tests of the gate functions — faster than running the
    whole audit script for each."""

    def test_can_import_audit_module(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        try:
            import audit  # noqa: F401
        except ImportError as e:
            pytest.fail(f"scripts/audit.py won't import: {e}")

    def test_gates_list_is_complete(self):
        sys.path.insert(0, str(ROOT / "scripts"))
        import audit
        gate_ids = {gid for gid, _ in audit.GATES}
        # Must have the full 12 we documented
        assert gate_ids == {"G1", "G2", "G3", "G4", "G5", "G6",
                            "G7", "G8", "G9", "G10", "G11", "G12",
                            "G13", "G14"}
