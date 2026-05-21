"""tests/test_flexcube_pipeline.py — Structural validation of the
FLEXCUBE pipeline validator (Standard #6, v5.35).

These tests don't run the full validator (which would need a live
FLEXCUBE for L1/L4/L5). They verify the script has the expected
shape: all five level functions exist, the spec thresholds are
encoded correctly, the mode-aware skipping is wired, and the artifact
contract that G20 depends on is well-formed.

Static + import-level only. Catches drift like "someone removed L4"
or "someone changed the artifact key from 'levels' to 'results'"
which would silently break G20.
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
ARTIFACT = ROOT / "flexcube_validation_results.json"


# ═══════════════════════════════════════════════════════════════════════
# Script presence + structure
# ═══════════════════════════════════════════════════════════════════════

class TestValidatorPresent:
    """The validator script must exist and be importable."""

    def test_script_exists(self):
        assert SCRIPT.exists(), f"Missing validator: {SCRIPT.relative_to(ROOT)}"

    def test_script_has_main_function(self):
        src = SCRIPT.read_text(encoding="utf-8")
        assert re.search(r"^def main\b", src, re.MULTILINE), (
            "validator script has no main() function"
        )

    def test_script_has_all_five_levels(self):
        """L1-L5 are the five Standard #6 levels. Each must be a
        separate run_lN_* function."""
        src = SCRIPT.read_text(encoding="utf-8")
        for n, name in [(1, "connectivity"), (2, "schema"),
                        (3, "data_types"), (4, "sample_data"),
                        (5, "full_sync")]:
            assert re.search(rf"^def run_l{n}_{name}\b", src, re.MULTILINE), (
                f"validator missing run_l{n}_{name}() function"
            )


class TestValidatorContracts:
    """The validator's internal contracts (EXPECTED_SCHEMAS, TYPE_CONTRACT)
    must align with the adapter, not the staging tables."""

    def test_expected_schemas_match_adapter(self):
        """L2's EXPECTED_SCHEMAS describes what the adapter MUST return.
        Required keys must be drawn from the adapter's documented
        contract (cif/name for customers, account_no/branch for
        accounts, loan_id/cif for loans). Drifting back to staging
        names (customer_id/customer_name) would break L2 in synthetic mode."""
        src = SCRIPT.read_text(encoding="utf-8")
        # The adapter contract uses cif (not customer_id) and name (not customer_name)
        assert '"cif"' in src, (
            "validator no longer references cif — adapter contract drift?"
        )
        # And conversely, customer_id should NOT appear in EXPECTED_SCHEMAS
        # required_keys (it's the staging column, set by ETL after translation)
        m = re.search(
            r"EXPECTED_SCHEMAS\s*=\s*\{(.+?)\}\s*\n\s*#",
            src, re.DOTALL,
        )
        assert m is not None, "EXPECTED_SCHEMAS dict not found at all"
        # Required-keys lines should not contain 'customer_id' (that's
        # a staging name; the adapter uses 'cif')
        body = m.group(1)
        # Find all required_keys sets
        for rq_match in re.finditer(r'"required_keys"\s*:\s*\{([^}]+)\}', body):
            keys_str = rq_match.group(1)
            assert "customer_id" not in keys_str, (
                f"required_keys contains staging name 'customer_id' — should be 'cif'. "
                f"Saw: {keys_str.strip()}"
            )
            assert "customer_name" not in keys_str, (
                f"required_keys contains staging name 'customer_name' — should be 'name'. "
                f"Saw: {keys_str.strip()}"
            )

    def test_type_contract_uses_adapter_field_names(self):
        """L3's TYPE_CONTRACT also uses adapter names (the layer L3
        actually inspects)."""
        src = SCRIPT.read_text(encoding="utf-8")
        m = re.search(r"TYPE_CONTRACT\s*=\s*\{(.+?)^\}", src, re.DOTALL | re.MULTILINE)
        assert m is not None, "TYPE_CONTRACT dict not found"
        body = m.group(1)
        # cif/loan_id/account_no must appear
        for adapter_name in ["cif", "loan_id", "account_no"]:
            assert f'"{adapter_name}"' in body, (
                f"TYPE_CONTRACT missing adapter field {adapter_name!r}"
            )

    def test_spec_thresholds_constants(self):
        """The five Standard #6 thresholds must be findable as constants
        or comparisons. L2=100%, L3=0 errors, L4=99%, L5=0 lost."""
        src = SCRIPT.read_text(encoding="utf-8")
        # Look for the SPEC_THRESHOLDS dict or similar
        # The exact form may evolve; just check the key targets are referenced
        assert re.search(r"\b100\b", src), "100% threshold not found anywhere"
        assert re.search(r"\b99\b", src), "99% threshold not found anywhere"


# ═══════════════════════════════════════════════════════════════════════
# Mode-aware skipping (synthetic/mock/live)
# ═══════════════════════════════════════════════════════════════════════

class TestModeAwareness:
    """The validator must respect adapter mode. Synthetic skips L1/L4/L5;
    mock skips L1; live runs all five."""

    def test_l1_skips_in_synthetic_mode(self):
        src = SCRIPT.read_text(encoding="utf-8")
        # Find run_l1 body
        m = re.search(r"def run_l1_connectivity\b.*?(?=\ndef |\Z)", src, re.DOTALL)
        assert m is not None
        body = m.group(0)
        # Must check mode and skip if not live
        assert "synthetic" in body or "live" in body, (
            "L1 has no mode awareness — would always run"
        )

    def test_l4_skips_in_synthetic_mode(self):
        src = SCRIPT.read_text(encoding="utf-8")
        m = re.search(r"def run_l4_sample_data\b.*?(?=\ndef |\Z)", src, re.DOTALL)
        assert m is not None
        body = m.group(0)
        assert "synthetic" in body or "skipped" in body, (
            "L4 doesn't skip in synthetic mode — there's no source-of-truth count"
        )

    def test_l5_skips_in_non_live_mode(self):
        src = SCRIPT.read_text(encoding="utf-8")
        m = re.search(r"def run_l5_full_sync\b.*?(?=\ndef |\Z)", src, re.DOTALL)
        assert m is not None
        body = m.group(0)
        assert "skipped" in body or "live" in body, (
            "L5 has no mode-skip path — full-sync test only meaningful live"
        )


# ═══════════════════════════════════════════════════════════════════════
# Artifact contract — what G20 reads
# ═══════════════════════════════════════════════════════════════════════

class TestArtifactContract:
    """The artifact written by the validator must contain the exact keys
    G20 reads. Drift here silently breaks the audit gate."""

    REQUIRED_TOP_KEYS = {
        "schema_version", "run_at", "configured_mode", "effective_mode",
        "levels", "summary", "all_passed", "any_failed",
    }

    REQUIRED_LEVEL_KEYS = {"level", "name", "status", "metric", "details", "duration_s"}

    REQUIRED_SUMMARY_KEYS = {"total_levels", "passed", "failed", "skipped"}

    @pytest.fixture(scope="class")
    def artifact(self) -> dict:
        """Run the validator (synthetic mode, no args) and parse the
        artifact. If the artifact already exists from a previous run
        we still re-run to make sure it reflects current code."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT)],
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=60,
        )
        # Exit code 0 means all passed/skipped cleanly. Anything else
        # is informational here — we still want to inspect the artifact.
        assert ARTIFACT.exists(), (
            f"validator did not produce {ARTIFACT}. "
            f"stdout={result.stdout!r}, stderr={result.stderr!r}"
        )
        return json.loads(ARTIFACT.read_text())

    def test_artifact_has_required_top_keys(self, artifact):
        missing = self.REQUIRED_TOP_KEYS - set(artifact.keys())
        assert not missing, f"artifact missing top-level keys: {sorted(missing)}"

    def test_artifact_has_five_levels(self, artifact):
        levels = artifact.get("levels", [])
        assert len(levels) == 5, f"expected 5 levels, got {len(levels)}"
        ids = {lvl.get("level") for lvl in levels}
        assert ids == {"L1", "L2", "L3", "L4", "L5"}, (
            f"levels missing or extra: {sorted(ids)}"
        )

    def test_each_level_has_required_keys(self, artifact):
        for lvl in artifact.get("levels", []):
            missing = self.REQUIRED_LEVEL_KEYS - set(lvl.keys())
            assert not missing, (
                f"level {lvl.get('level')} missing keys: {sorted(missing)}"
            )

    def test_summary_block_has_required_keys(self, artifact):
        summary = artifact.get("summary", {})
        missing = self.REQUIRED_SUMMARY_KEYS - set(summary.keys())
        assert not missing, f"summary missing keys: {sorted(missing)}"

    def test_synthetic_mode_skips_l1_l4_l5(self, artifact):
        """In synthetic mode (the validator's default), L1/L4/L5 must
        report skipped, while L2/L3 actually run."""
        if artifact.get("effective_mode") != "synthetic":
            pytest.skip("not in synthetic mode")
        by_id = {lvl["level"]: lvl for lvl in artifact["levels"]}
        for lvl_id in ("L1", "L4", "L5"):
            assert by_id[lvl_id]["status"] == "skipped", (
                f"{lvl_id} should be skipped in synthetic mode, "
                f"got {by_id[lvl_id]['status']}"
            )
        for lvl_id in ("L2", "L3"):
            assert by_id[lvl_id]["status"] in ("passed", "failed"), (
                f"{lvl_id} should run in synthetic mode, "
                f"got {by_id[lvl_id]['status']}"
            )

    def test_synthetic_mode_l2_passes(self, artifact):
        """After v5.35's adapter-contract fix, L2 must pass in synthetic mode."""
        if artifact.get("effective_mode") != "synthetic":
            pytest.skip("not in synthetic mode")
        by_id = {lvl["level"]: lvl for lvl in artifact["levels"]}
        assert by_id["L2"]["status"] == "passed", (
            f"L2 fails in synthetic mode — adapter/EXPECTED_SCHEMAS drift. "
            f"Details: {by_id['L2'].get('details')}"
        )

    def test_synthetic_mode_l3_passes(self, artifact):
        if artifact.get("effective_mode") != "synthetic":
            pytest.skip("not in synthetic mode")
        by_id = {lvl["level"]: lvl for lvl in artifact["levels"]}
        assert by_id["L3"]["status"] == "passed", (
            f"L3 fails in synthetic mode — TYPE_CONTRACT drift. "
            f"Details: {by_id['L3'].get('details')}"
        )


# ═══════════════════════════════════════════════════════════════════════
# Driver behaviour — exit codes + CLI flags
# ═══════════════════════════════════════════════════════════════════════

class TestDriverBehaviour:
    """The validator's CLI must support the documented flags."""

    def test_help_works(self):
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--help"],
            cwd=ROOT, capture_output=True, text=True, timeout=10,
        )
        assert result.returncode == 0
        assert "--mode" in result.stdout
        assert "--levels" in result.stdout

    def test_levels_flag_filters_run_set(self):
        """--levels=L2,L3 should only run L2 and L3."""
        result = subprocess.run(
            [sys.executable, str(SCRIPT), "--levels=L2,L3"],
            cwd=ROOT, capture_output=True, text=True, timeout=30,
        )
        # Exit code is 0 (passed) or 1 (failed); not a crash
        assert result.returncode in (0, 1, 2), (
            f"unexpected exit code {result.returncode}; stderr={result.stderr!r}"
        )
        if ARTIFACT.exists():
            data = json.loads(ARTIFACT.read_text())
            ran_levels = [lvl for lvl in data["levels"] if lvl["status"] != "skipped"]
            ran_ids = {lvl["level"] for lvl in ran_levels}
            # L1/L4/L5 may be skipped due to mode, but the LEVELS flag
            # should also skip L1 here. Bottom line: only L2 and L3 may
            # have run.
            assert ran_ids.issubset({"L2", "L3"}), (
                f"--levels=L2,L3 ran extra levels: {ran_ids - {'L2', 'L3'}}"
            )


# ═══════════════════════════════════════════════════════════════════════
# Integration with G20 — the audit gate must read the artifact correctly
# ═══════════════════════════════════════════════════════════════════════

class TestG20Integration:
    """Verify G20 in scripts/audit.py reads the artifact this validator
    produces. Catches schema drift between writer and reader."""

    def test_g20_reads_synthetic_artifact_as_pass(self):
        """After running the validator in synthetic mode, G20 should
        report PASS (because L1/L4/L5 are correctly skipped)."""
        # Run validator first so artifact exists
        subprocess.run(
            [sys.executable, str(SCRIPT)],
            cwd=ROOT, capture_output=True, text=True, timeout=60,
        )
        # Now invoke just G20 from audit.py
        result = subprocess.run(
            [sys.executable, str(ROOT / "scripts" / "audit.py"),
             "--gate=G20"],
            cwd=ROOT, capture_output=True, text=True, timeout=30,
        )
        # The audit script may or may not support --gate filtering; if
        # not, run the whole audit and check just G20's line
        out = result.stdout
        if "G20" not in out:
            # Run full audit
            full = subprocess.run(
                [sys.executable, str(ROOT / "scripts" / "audit.py")],
                cwd=ROOT, capture_output=True, text=True, timeout=60,
            )
            out = full.stdout
        assert "G20" in out, "audit script did not report G20"
        # G20 line should show ✅
        for line in out.split("\n"):
            if "G20" in line:
                assert "✅" in line or "PASS" in line, (
                    f"G20 should pass in synthetic mode, got: {line.strip()}"
                )
                break
