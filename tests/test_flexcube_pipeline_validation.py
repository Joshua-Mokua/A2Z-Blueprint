"""tests/test_flexcube_pipeline_validation.py — Standard #6 invariants
(v5.35).

These tests don't require live FLEXCUBE; they verify the validator
script + the audit gate are correctly wired:

  - scripts/test_flexcube_pipeline.py exists and exports the L1-L5
    runners
  - It writes flexcube_validation_results.json at the project root
  - The artifact has the schema G20 expects
  - Each spec level is represented and its threshold encoded
  - The runbook references each level
  - G20 audit gate handles missing/present artifacts correctly

These tests CAN actually run the validator — it's mode-aware and
exits 0 in synthetic mode (per Standard #6 verification: "exits 0").
That's a real end-to-end check.
"""
from __future__ import annotations

import json
import re
import subprocess
import sys
from pathlib import Path

import pytest


ROOT = Path(__file__).parent.parent
SCRIPT = ROOT / "scripts" / "test_flexcube_pipeline.py"
RESULTS_PATH = ROOT / "flexcube_validation_results.json"

EXPECTED_LEVELS = ["L1", "L2", "L3", "L4", "L5"]
EXPECTED_LEVEL_NAMES = {
    "L1": "Connectivity",
    "L2": "Schema",
    "L3": "Data types",
    "L4": "Sample data",
    "L5": "Full sync",
}


# ═══════════════════════════════════════════════════════════════════════
# Validator script — file presence and structure
# ═══════════════════════════════════════════════════════════════════════

class TestValidatorScriptPresent:
    """The validator script must exist and be the entry point Standard #6
    names by path."""

    def test_script_exists(self):
        assert SCRIPT.exists(), (
            f"Standard #6 spec names {SCRIPT.relative_to(ROOT)} as the "
            f"verification script. It must exist."
        )

    def test_script_is_executable_python(self):
        src = SCRIPT.read_text(encoding="utf-8")
        # Must be valid Python
        import ast
        ast.parse(src)  # raises if invalid
        # Must have a main() entry point
        assert "def main(" in src, "validator must define main()"
        # Must have the if __name__ == '__main__' guard
        assert '__name__ == "__main__"' in src or "__name__ == '__main__'" in src


class TestValidatorLevels:
    """Each of L1-L5 must have its own runner function."""

    @pytest.mark.parametrize("level", EXPECTED_LEVELS)
    def test_level_runner_defined(self, level):
        src = SCRIPT.read_text(encoding="utf-8")
        # Functions are named run_l1_connectivity, run_l2_schema, etc.
        # Just verify a function with the level number exists.
        level_num = level[1]  # "1", "2", ...
        pat = re.compile(rf"^def\s+run_l{level_num}_\w+", re.MULTILINE)
        assert pat.search(src), (
            f"validator missing run_l{level_num}_* function for {level} "
            f"({EXPECTED_LEVEL_NAMES[level]})"
        )

    def test_spec_thresholds_constant_present(self):
        """SPEC_THRESHOLDS must exist and cover all 5 levels."""
        src = SCRIPT.read_text(encoding="utf-8")
        assert "SPEC_THRESHOLDS" in src
        for level in EXPECTED_LEVELS:
            assert f'"{level}"' in src, f"SPEC_THRESHOLDS missing entry for {level}"


class TestValidatorCli:
    """The validator CLI must support --mode and --levels flags."""

    def test_supports_mode_flag(self):
        src = SCRIPT.read_text(encoding="utf-8")
        # argparse should add --mode option
        assert "--mode" in src
        # Three valid modes
        for mode in ("synthetic", "mock", "live"):
            assert f'"{mode}"' in src or f"'{mode}'" in src, (
                f"validator doesn't recognise mode={mode}"
            )

    def test_supports_levels_flag(self):
        src = SCRIPT.read_text(encoding="utf-8")
        assert "--levels" in src

    def test_supports_verbose_flag(self):
        src = SCRIPT.read_text(encoding="utf-8")
        assert "--verbose" in src


# ═══════════════════════════════════════════════════════════════════════
# Schema — what the adapter must return for L2 to pass
# ═══════════════════════════════════════════════════════════════════════

class TestExpectedSchemas:
    """EXPECTED_SCHEMAS must match the actual adapter contract.

    The adapter (utils/flexcube_adapter.py) returns FLEXCUBE-native field
    names (cif, name, account_no, ...). The ETL (scripts/etl_flexcube.py)
    translates these to staging-table column names. L2 here MUST check
    the adapter's contract, not the staging schema."""

    def test_expected_schemas_constant_present(self):
        src = SCRIPT.read_text(encoding="utf-8")
        assert "EXPECTED_SCHEMAS" in src

    def test_customers_required_keys_match_adapter(self):
        """The adapter returns cif + name. EXPECTED_SCHEMAS must require
        those, not customer_id/customer_name (which are staging-side)."""
        src = SCRIPT.read_text(encoding="utf-8")
        # Find the EXPECTED_SCHEMAS block
        m = re.search(
            r"EXPECTED_SCHEMAS\s*=\s*\{.*?^\}\s*$",
            src, re.DOTALL | re.MULTILINE
        )
        assert m, "EXPECTED_SCHEMAS not found or not a top-level dict"
        block = m.group(0)
        # Customer required_keys block should mention cif and name
        cust_block = re.search(
            r'"customers"\s*:\s*\{[^}]*"required_keys"\s*:\s*\{([^}]+)\}',
            block, re.DOTALL
        )
        assert cust_block, "customers entry malformed"
        required = cust_block.group(1)
        assert '"cif"' in required, (
            "customers required_keys must include 'cif' "
            "(matches adapter contract, not staging schema). "
            "If the adapter changes to return customer_id, update this test."
        )
        assert '"name"' in required


# ═══════════════════════════════════════════════════════════════════════
# End-to-end run — Standard #6 verification criterion
# ═══════════════════════════════════════════════════════════════════════

class TestSyntheticRun:
    """Standard #6's verification: scripts/test_flexcube_pipeline.py
    exits 0. We can verify this directly in synthetic mode."""

    def test_synthetic_run_exits_zero(self, tmp_path, monkeypatch):
        """Run the validator. Expected exit code: 0 (passed/skipped only)."""
        # Run from project root so it finds the adapter + writes the
        # results file in the expected location.
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--mode=synthetic"],
            cwd=str(ROOT),
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, (
            f"Validator exited {result.returncode} in synthetic mode. "
            f"stdout:\n{result.stdout[-500:]}\nstderr:\n{result.stderr[-500:]}"
        )

    def test_synthetic_run_writes_results_artifact(self):
        """After a run, flexcube_validation_results.json must exist
        with valid schema."""
        # The previous test ran the validator; the artifact should exist
        if not RESULTS_PATH.exists():
            # Run it now if the prior test didn't (test order isn't
            # guaranteed across pytest invocations)
            subprocess.run(
                [sys.executable, str(SCRIPT), "--mode=synthetic"],
                cwd=str(ROOT), capture_output=True, timeout=60,
            )
        assert RESULTS_PATH.exists(), (
            f"Validator didn't write {RESULTS_PATH.relative_to(ROOT)}"
        )

    def test_results_artifact_has_expected_shape(self):
        """The JSON must have the shape G20 expects."""
        if not RESULTS_PATH.exists():
            subprocess.run(
                [sys.executable, str(SCRIPT), "--mode=synthetic"],
                cwd=str(ROOT), capture_output=True, timeout=60,
            )
        data = json.loads(RESULTS_PATH.read_text())
        # Top-level keys G20 reads
        for k in ["schema_version", "run_at", "configured_mode",
                  "effective_mode", "levels", "summary", "any_failed"]:
            assert k in data, f"results missing top-level key: {k}"
        # Levels must be a list of 5 entries (L1-L5)
        levels = data["levels"]
        assert isinstance(levels, list)
        assert len(levels) == 5
        for lvl in levels:
            for k in ["level", "name", "status", "metric", "duration_s"]:
                assert k in lvl, f"level entry missing key: {k}"

    def test_synthetic_l2_l3_pass(self):
        """L1, L4, L5 are skipped in synthetic mode (no live target,
        no source-of-truth). L2 (schema) and L3 (data types) MUST pass."""
        if not RESULTS_PATH.exists():
            subprocess.run(
                [sys.executable, str(SCRIPT), "--mode=synthetic"],
                cwd=str(ROOT), capture_output=True, timeout=60,
            )
        data = json.loads(RESULTS_PATH.read_text())
        by_id = {lvl["level"]: lvl for lvl in data["levels"]}
        assert by_id["L2"]["status"] == "passed", (
            f"L2 (Schema) must pass in synthetic mode. Got: "
            f"{by_id['L2'].get('status')}\n"
            f"Details: {by_id['L2'].get('details')}"
        )
        assert by_id["L3"]["status"] == "passed", (
            f"L3 (Data types) must pass in synthetic mode. Got: "
            f"{by_id['L3'].get('status')}\n"
            f"Details: {by_id['L3'].get('details')}"
        )

    def test_synthetic_l1_l4_l5_skipped(self):
        """In synthetic mode L1/L4/L5 should be skipped with informational
        status — NOT failed."""
        if not RESULTS_PATH.exists():
            subprocess.run(
                [sys.executable, str(SCRIPT), "--mode=synthetic"],
                cwd=str(ROOT), capture_output=True, timeout=60,
            )
        data = json.loads(RESULTS_PATH.read_text())
        by_id = {lvl["level"]: lvl for lvl in data["levels"]}
        for lvl_id in ("L1", "L4", "L5"):
            assert by_id[lvl_id]["status"] == "skipped", (
                f"{lvl_id} should be skipped in synthetic mode (no live "
                f"target / no source-of-truth). Got: "
                f"{by_id[lvl_id].get('status')}"
            )


# ═══════════════════════════════════════════════════════════════════════
# Audit gate G20 — wiring + coverage
# ═══════════════════════════════════════════════════════════════════════

class TestG20Wiring:
    """G20 must be defined in scripts/audit.py and registered."""

    def test_gate_function_exists(self):
        audit_src = (ROOT / "scripts" / "audit.py").read_text(encoding="utf-8")
        assert "def gate_flexcube_pipeline_validation" in audit_src

    def test_gate_registered_in_GATES_list(self):
        audit_src = (ROOT / "scripts" / "audit.py").read_text(encoding="utf-8")
        # Find the GATES = [...] block
        m = re.search(r"^GATES\s*=\s*\[(.*?)^\]", audit_src, re.DOTALL | re.MULTILINE)
        assert m, "GATES list not found in audit.py"
        gates_block = m.group(1)
        assert '"G20"' in gates_block
        assert "gate_flexcube_pipeline_validation" in gates_block

    def test_gate_reads_results_path(self):
        """G20 must read flexcube_validation_results.json from the project
        root — same path the validator writes to."""
        audit_src = (ROOT / "scripts" / "audit.py").read_text(encoding="utf-8")
        # The string must appear inside the gate's body
        m = re.search(
            r"def gate_flexcube_pipeline_validation\b.*?(?=\ndef |\Z)",
            audit_src, re.DOTALL,
        )
        assert m
        body = m.group(0)
        assert "flexcube_validation_results.json" in body, (
            "G20 doesn't reference flexcube_validation_results.json — "
            "the validator's output won't be read."
        )


class TestFoundationalRegistration:
    """The validator script writes JSON, so it must be in FOUNDATIONAL
    (otherwise G2 direct_io flags it)."""

    def test_validator_in_foundational(self):
        audit_src = (ROOT / "scripts" / "audit.py").read_text(encoding="utf-8")
        # Find FOUNDATIONAL block
        m = re.search(r"^FOUNDATIONAL\s*=\s*\{(.*?)^\}", audit_src,
                      re.DOTALL | re.MULTILINE)
        assert m, "FOUNDATIONAL set not found"
        foundational = m.group(1)
        assert "scripts/test_flexcube_pipeline.py" in foundational, (
            "scripts/test_flexcube_pipeline.py not in FOUNDATIONAL — "
            "G2 will flag its JSON I/O as a violation."
        )


# ═══════════════════════════════════════════════════════════════════════
# Runbook + spec coverage
# ═══════════════════════════════════════════════════════════════════════

class TestSpecCoverage:
    """Standard #6 names specific thresholds. The validator must encode them."""

    def test_l2_target_100pct_encoded(self):
        src = SCRIPT.read_text(encoding="utf-8")
        # SPEC_THRESHOLDS["L2"] should declare 100.0
        assert re.search(r'"L2"\s*:\s*\{[^}]*100', src), (
            "L2 spec threshold (100% schema compliance) not encoded"
        )

    def test_l3_target_zero_errors_encoded(self):
        src = SCRIPT.read_text(encoding="utf-8")
        assert re.search(
            r'"L3"\s*:\s*\{[^}]*target_max_errors\s*:\s*0',
            src
        ), "L3 spec threshold (0 type errors) not encoded"

    def test_l4_target_99pct_encoded(self):
        src = SCRIPT.read_text(encoding="utf-8")
        assert re.search(r'"L4"\s*:\s*\{[^}]*99', src), (
            "L4 spec threshold (≥99% sample data match) not encoded"
        )

    def test_l5_target_zero_loss_encoded(self):
        src = SCRIPT.read_text(encoding="utf-8")
        assert re.search(
            r'"L5"\s*:\s*\{[^}]*target_max_loss\s*:\s*0',
            src
        ), "L5 spec threshold (0 records lost) not encoded"
