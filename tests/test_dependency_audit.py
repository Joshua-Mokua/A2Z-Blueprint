"""tests/test_dependency_audit.py — Standard #9 invariants (v5.37).

Structural tests that verify the dependency-security framework is wired
correctly. They don't run pip-audit / safety themselves (that needs
network + the tools installed); they verify:

  - scripts/run_dependency_audit.py exists and is well-formed
  - It produces dependency_audit_results.json with the schema G21 reads
  - .cve-ignore.json exists and is valid JSON
  - requirements.txt is split (runtime) from requirements-dev.txt (test/dev)
  - The CI workflow exists and is set up correctly
  - G21 is registered in the audit GATES list
"""
from __future__ import annotations

import json
import re
from pathlib import Path

import pytest


ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "scripts" / "run_dependency_audit.py"
ARTIFACT = ROOT / "dependency_audit_results.json"
IGNORE = ROOT / ".cve-ignore.json"


# ═══════════════════════════════════════════════════════════════════════
# Files exist
# ═══════════════════════════════════════════════════════════════════════

class TestFilesPresent:
    """Each Standard #9 file must exist."""

    def test_runner_script_exists(self):
        assert SCRIPT.exists(), (
            "scripts/run_dependency_audit.py is the entry point for "
            "Standard #9. G21 expects it to produce dependency_audit_results.json."
        )

    def test_cve_ignore_file_exists(self):
        assert IGNORE.exists(), (
            ".cve-ignore.json must exist (even if empty []). The runner "
            "treats a missing file as 'no suppressions' silently, which "
            "is fine — but a present empty file is the canonical state."
        )

    def test_cve_ignore_is_valid_json(self):
        try:
            data = json.loads(IGNORE.read_text())
        except json.JSONDecodeError as e:
            pytest.fail(f".cve-ignore.json is not valid JSON: {e}")
        assert isinstance(data, list), (
            ".cve-ignore.json must be a JSON list of suppression objects"
        )

    def test_workflow_exists(self):
        wf = ROOT / ".github" / "workflows" / "depaudit.yml"
        assert wf.exists(), "Missing .github/workflows/depaudit.yml"


# ═══════════════════════════════════════════════════════════════════════
# Requirements split
# ═══════════════════════════════════════════════════════════════════════

class TestRequirementsSplit:
    """Standard #9 requires runtime/dev separation so the gate scans
    only production deps."""

    def test_requirements_dev_exists(self):
        assert (ROOT / "requirements-dev.txt").exists(), (
            "requirements-dev.txt must exist — Standard #9 requires "
            "splitting test/dev deps from production."
        )

    def test_pytest_in_dev_not_runtime(self):
        runtime = (ROOT / "requirements.txt").read_text().lower()
        dev     = (ROOT / "requirements-dev.txt").read_text().lower()
        assert "pytest" in dev, (
            "pytest belongs in requirements-dev.txt (it never ships to production)"
        )
        # Runtime should NOT have pytest — but allow comments mentioning it
        runtime_no_comments = "\n".join(
            l for l in runtime.split("\n") if not l.strip().startswith("#")
        )
        assert "pytest" not in runtime_no_comments, (
            "pytest must not appear in runtime requirements.txt — move to "
            "requirements-dev.txt"
        )

    def test_pip_audit_and_safety_in_dev(self):
        dev = (ROOT / "requirements-dev.txt").read_text().lower()
        assert "pip-audit" in dev, "pip-audit must be in requirements-dev.txt"
        assert "safety" in dev, "safety must be in requirements-dev.txt"

    def test_runtime_keeps_bcrypt(self):
        """bcrypt is V-004 mitigation — it MUST be a runtime dep."""
        runtime = (ROOT / "requirements.txt").read_text().lower()
        assert "bcrypt" in runtime, (
            "bcrypt must be in runtime requirements.txt — it's V-004 mitigation"
        )


# ═══════════════════════════════════════════════════════════════════════
# Runner script structure
# ═══════════════════════════════════════════════════════════════════════

class TestRunnerStructure:
    """The runner must have the API G21 depends on."""

    def test_runner_writes_expected_artifact_path(self):
        src = SCRIPT.read_text()
        assert "dependency_audit_results.json" in src, (
            "Runner must write to dependency_audit_results.json — "
            "G21 reads that exact filename"
        )

    def test_runner_invokes_pip_audit(self):
        src = SCRIPT.read_text()
        assert "pip-audit" in src

    def test_runner_invokes_safety(self):
        src = SCRIPT.read_text()
        assert "safety" in src

    def test_runner_loads_cve_ignore(self):
        src = SCRIPT.read_text()
        assert ".cve-ignore.json" in src or "cve-ignore" in src

    def test_runner_documents_exit_codes(self):
        src = SCRIPT.read_text()
        # Docstring should describe the three exit codes
        assert "0" in src and "1" in src and "2" in src
        # Find the exit code section
        assert "Exit code" in src or "exit code" in src or "exit_code" in src


# ═══════════════════════════════════════════════════════════════════════
# G21 gate registration + behaviour
# ═══════════════════════════════════════════════════════════════════════

class TestG21Wiring:
    """G21 must be defined in audit.py and registered in GATES."""

    def test_g21_function_defined(self):
        audit_src = (ROOT / "scripts" / "audit.py").read_text()
        assert "def gate_dependency_security" in audit_src, (
            "G21 function gate_dependency_security must be defined in "
            "scripts/audit.py"
        )

    def test_g21_in_gates_list(self):
        audit_src = (ROOT / "scripts" / "audit.py").read_text()
        assert '("G21", gate_dependency_security)' in audit_src, (
            "G21 must be registered in the GATES list at the bottom of "
            "scripts/audit.py — otherwise it's defined but not run"
        )

    def test_g21_reads_correct_artifact_path(self):
        audit_src = (ROOT / "scripts" / "audit.py").read_text()
        # G21 must reference the same filename the runner writes
        assert "dependency_audit_results.json" in audit_src, (
            "G21 must read dependency_audit_results.json — the runner's "
            "output filename"
        )

    def test_g21_handles_scanner_unavailable(self):
        """G21 must treat 'scanner_unavailable' as informational."""
        audit_src = (ROOT / "scripts" / "audit.py").read_text()
        assert "scanner_unavailable" in audit_src, (
            "G21 must distinguish 'scanner_unavailable' (informational) "
            "from real findings — check the gate's status handling"
        )


# ═══════════════════════════════════════════════════════════════════════
# CI workflow shape
# ═══════════════════════════════════════════════════════════════════════

class TestCiWorkflow:
    """The depaudit workflow must be manual + scheduled (not push-triggered)."""

    WORKFLOW = ROOT / ".github" / "workflows" / "depaudit.yml"

    def test_workflow_uses_workflow_dispatch(self):
        src = self.WORKFLOW.read_text()
        assert "workflow_dispatch" in src, (
            "Dependency audit should be manually triggerable for ad-hoc "
            "investigation"
        )

    def test_workflow_has_schedule(self):
        src = self.WORKFLOW.read_text()
        assert "schedule:" in src, (
            "Dependency audit should run on a schedule — CVE databases "
            "update continuously, so even unchanged code can develop new "
            "vulnerabilities"
        )
        assert "cron:" in src

    def test_workflow_installs_dev_deps(self):
        src = self.WORKFLOW.read_text()
        assert "requirements-dev.txt" in src, (
            "Workflow must install requirements-dev.txt to get pip-audit + safety"
        )

    def test_workflow_runs_runner(self):
        src = self.WORKFLOW.read_text()
        assert "scripts/run_dependency_audit.py" in src

    def test_workflow_uploads_artifact(self):
        src = self.WORKFLOW.read_text()
        assert "upload-artifact" in src, (
            "Scanner outputs must be uploaded — operators need to see "
            "individual CVE details, not just gate pass/fail"
        )

    def test_workflow_reruns_audit_after_scan(self):
        src = self.WORKFLOW.read_text()
        assert "scripts/audit.py" in src, (
            "Workflow must re-run scripts/audit.py at the end so G21 "
            "picks up the freshly written artifact"
        )


# ═══════════════════════════════════════════════════════════════════════
# Suppression file format
# ═══════════════════════════════════════════════════════════════════════

class TestSuppressionFormat:
    """Each suppression in .cve-ignore.json must have id + reason."""

    def test_suppressions_have_required_fields(self):
        data = json.loads(IGNORE.read_text())
        for i, item in enumerate(data):
            assert isinstance(item, dict), (
                f"Suppression #{i} is not a dict: {item!r}"
            )
            assert "id" in item, (
                f"Suppression #{i} missing 'id' field — required so the "
                f"runner can match against scanner findings"
            )
            assert "reason" in item, (
                f"Suppression #{i} ({item.get('id')}) missing 'reason' — "
                f"every suppression needs a documented justification"
            )
            # Optional but recommended: expires
            if "expires" in item:
                # Must be YYYY-MM-DD
                assert re.match(r"^\d{4}-\d{2}-\d{2}$", item["expires"]), (
                    f"Suppression {item['id']} has malformed 'expires' "
                    f"date: {item['expires']!r} (want YYYY-MM-DD)"
                )

    def test_suppressions_count_is_low(self):
        """Sanity check: too many suppressions means we're papering over
        real issues. Warn if more than 10."""
        data = json.loads(IGNORE.read_text())
        # Soft cap — fail at 20, warn between 10-20
        assert len(data) < 20, (
            f"Too many active suppressions ({len(data)}). Each one is a "
            f"deferred risk decision. Review them and remediate or set "
            f"expiration dates."
        )
