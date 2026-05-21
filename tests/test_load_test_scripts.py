"""tests/test_load_test_scripts.py — Structural validation of k6 load test
scripts (Standard #5, v5.34).

These tests don't run k6 (which would need a target environment); they
verify the scripts have the expected shape:

  - Each .js file in tests/load/ exists and imports the auth helper
  - The driver script scripts/run_load_tests.py recognises each test
  - The CI workflow at .github/workflows/loadtest.yml is well-formed
  - The runbook docs/LOAD_TESTING_RUNBOOK.md exists and references each test

Static validation only. Catches drift like "someone added a new k6 script
but forgot to register it in the runner" — which would silently leave
that scenario unmeasured.
"""
from __future__ import annotations

import re
from pathlib import Path

import pytest


ROOT = Path(__file__).parent.parent
LOAD_DIR = ROOT / "tests" / "load"

EXPECTED_SCRIPTS = {
    "baseline_smoke",
    "api_p95",
    "concurrent_users",
    "export_10k",
}


# ═══════════════════════════════════════════════════════════════════════
# k6 scripts — file presence and basic structure
# ═══════════════════════════════════════════════════════════════════════

class TestLoadScriptsPresent:
    """Each Standard #5 metric needs its own k6 script."""

    def test_load_dir_exists(self):
        assert LOAD_DIR.exists() and LOAD_DIR.is_dir()

    @pytest.mark.parametrize("name", sorted(EXPECTED_SCRIPTS))
    def test_script_exists(self, name):
        script = LOAD_DIR / f"{name}.js"
        assert script.exists(), f"Missing k6 script: tests/load/{name}.js"

    def test_lib_auth_exists(self):
        lib_auth = LOAD_DIR / "lib" / "auth.js"
        assert lib_auth.exists(), "Missing tests/load/lib/auth.js (shared JWT helper)"


class TestLoadScriptStructure:
    """Each k6 script must export `options` and a default function."""

    @pytest.mark.parametrize("name", sorted(EXPECTED_SCRIPTS))
    def test_script_exports_options(self, name):
        src = (LOAD_DIR / f"{name}.js").read_text(encoding="utf-8")
        # k6 looks for `export const options = { ... }`
        assert re.search(r"export\s+const\s+options\s*=", src), (
            f"{name}.js doesn't export options object"
        )

    @pytest.mark.parametrize("name", sorted(EXPECTED_SCRIPTS))
    def test_script_exports_default_function(self, name):
        src = (LOAD_DIR / f"{name}.js").read_text(encoding="utf-8")
        # k6 calls `export default function () { ... }`
        assert re.search(r"export\s+default\s+function", src), (
            f"{name}.js doesn't export default scenario function"
        )

    @pytest.mark.parametrize("name", sorted(EXPECTED_SCRIPTS - {"baseline_smoke"}))
    def test_authed_scripts_use_login(self, name):
        """Every script except baseline_smoke must auth via the helper.
        baseline_smoke hits /api/health which is the only unauthed endpoint."""
        src = (LOAD_DIR / f"{name}.js").read_text(encoding="utf-8")
        assert "login()" in src, (
            f"{name}.js doesn't call login() — its requests will be 401 in production"
        )

    @pytest.mark.parametrize("name", sorted(EXPECTED_SCRIPTS))
    def test_script_declares_thresholds(self, name):
        """Each script must declare at least one threshold; otherwise k6
        always exits 0 and the gate never sees failures."""
        src = (LOAD_DIR / f"{name}.js").read_text(encoding="utf-8")
        assert "thresholds" in src, (
            f"{name}.js options block has no thresholds — gate G19 can't fail"
        )


# ═══════════════════════════════════════════════════════════════════════
# Spec metric coverage — every Standard #5 target has a test
# ═══════════════════════════════════════════════════════════════════════

class TestSpecMetricCoverage:
    """The four Standard #5 targets must each be exercised by a script."""

    def test_api_p95_target_in_api_p95_script(self):
        src = (LOAD_DIR / "api_p95.js").read_text(encoding="utf-8")
        # Must declare a p95 < 200ms threshold
        assert re.search(r'http_req_duration["\']?\s*:\s*\[\s*["\']p\(95\)<200', src), (
            "api_p95.js doesn't declare http_req_duration p(95)<200 threshold"
        )

    def test_dashboard_p95_target_present(self):
        src = (LOAD_DIR / "api_p95.js").read_text(encoding="utf-8")
        # Dashboard sub-threshold
        assert re.search(r"kind\s*:\s*['\"]dashboard['\"]", src), (
            "api_p95.js doesn't tag any endpoint as kind:dashboard"
        )
        assert "p(95)<3000" in src or "p(95)<3000" in src.replace(" ", ""), (
            "api_p95.js doesn't enforce dashboard p(95)<3000"
        )

    def test_concurrent_users_targets_1000_vus(self):
        src = (LOAD_DIR / "concurrent_users.js").read_text(encoding="utf-8")
        # Spec demands 1,000+ concurrent users
        assert "1000" in src, "concurrent_users.js doesn't target 1000 VUs"

    def test_export_10k_targets_10s_threshold(self):
        src = (LOAD_DIR / "export_10k.js").read_text(encoding="utf-8")
        # Spec: export 10k rows < 10 seconds
        assert "10000" in src, "export_10k.js doesn't enforce 10000ms threshold"
        # And actually requests 10000 rows
        assert re.search(r'limit["\']?\s*:\s*10000', src), (
            "export_10k.js doesn't request 10000 rows"
        )


# ═══════════════════════════════════════════════════════════════════════
# Driver script — recognises every k6 script
# ═══════════════════════════════════════════════════════════════════════

class TestDriverScript:
    """scripts/run_load_tests.py must list every k6 script in TESTS."""

    def test_driver_exists(self):
        assert (ROOT / "scripts" / "run_load_tests.py").exists()

    def test_driver_lists_every_k6_script(self):
        src = (ROOT / "scripts" / "run_load_tests.py").read_text(encoding="utf-8")
        for name in EXPECTED_SCRIPTS:
            assert f'"{name}"' in src, (
                f"scripts/run_load_tests.py doesn't reference {name}"
            )

    def test_driver_writes_load_results_json(self):
        """The audit gate G19 reads load_results.json. The driver must
        write to that exact path."""
        src = (ROOT / "scripts" / "run_load_tests.py").read_text(encoding="utf-8")
        assert "load_results.json" in src, (
            "Driver doesn't write load_results.json — G19 will never see data"
        )


# ═══════════════════════════════════════════════════════════════════════
# CI workflow + runbook
# ═══════════════════════════════════════════════════════════════════════

class TestCiAndDocs:
    """Manual-trigger CI workflow + runbook must exist."""

    def test_loadtest_workflow_exists(self):
        wf = ROOT / ".github" / "workflows" / "loadtest.yml"
        assert wf.exists(), "Missing .github/workflows/loadtest.yml"

    def test_loadtest_workflow_is_manual_trigger(self):
        """Load tests should NOT run on every push. Manual trigger only."""
        wf_src = (ROOT / ".github" / "workflows" / "loadtest.yml").read_text(encoding="utf-8")
        assert "workflow_dispatch" in wf_src, (
            "loadtest.yml must use workflow_dispatch (manual trigger) — "
            "load tests are too slow for every-push CI"
        )

    def test_loadtest_workflow_installs_k6(self):
        wf_src = (ROOT / ".github" / "workflows" / "loadtest.yml").read_text(encoding="utf-8")
        assert "k6" in wf_src, "loadtest.yml doesn't install k6"

    def test_runbook_exists(self):
        rb = ROOT / "docs" / "LOAD_TESTING_RUNBOOK.md"
        assert rb.exists(), "Missing docs/LOAD_TESTING_RUNBOOK.md"

    def test_runbook_documents_every_script(self):
        rb_src = (ROOT / "docs" / "LOAD_TESTING_RUNBOOK.md").read_text(encoding="utf-8")
        for name in EXPECTED_SCRIPTS:
            assert name in rb_src, (
                f"Runbook doesn't document {name}.js"
            )

    def test_runbook_documents_all_four_spec_metrics(self):
        rb_src = (ROOT / "docs" / "LOAD_TESTING_RUNBOOK.md").read_text(encoding="utf-8")
        for target in ["200 ms", "3 s", "1,000+", "10 s"]:
            assert target in rb_src, f"Runbook doesn't mention spec target '{target}'"
