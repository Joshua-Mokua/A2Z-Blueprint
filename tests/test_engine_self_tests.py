"""tests/test_engine_self_tests.py — Pytest wrapper for the 152
utils/*.py modules with self_test() functions.

The platform has a long-standing engine self-test discipline: every
engine module exposes a `self_test()` function that exercises its
contract. `scripts/run_engine_self_tests.py` discovers and runs them
all; CI gates on it. But the runner is a standalone script — it
isn't pytest-driven, so `coverage.py` doesn't capture execution from
it.

This wrapper turns the 152 self-tests into 152 parameterized pytest
cases. Same discovery logic as `scripts/run_engine_self_tests.py`.
Same failure semantics. The point is visibility to `coverage.py`:
when this file runs under `pytest --cov`, every engine module gets
imported and exercised, so its lines count toward the coverage
totals.

Coverage gain estimate (v10.97 baseline = unknown):
  - 152 modules × ~5-10 KB code each = ~1MB of engine code
  - Most engines have rich self_tests (e.g., audit_trail_cert.py
    runs 30 internal _test_* functions; mlops_adjudication_log.py
    runs 21). So the line-coverage gain per module is significant.

What this file is NOT:
  - It's not a SUBSTITUTE for module-specific tests. The self_tests
    cover each engine's contract; module-specific tests cover
    integration with other modules + edge cases the self_test
    doesn't reach.
  - It's not exhaustive — modules without self_test() (e.g.,
    flexcube_adapter.py at v10.97) need separate tests written.

Future enhancement: a parallel test that imports every utils module
WITHOUT calling self_test, to surface import-time errors as pytest
failures (currently they'd surface as engine-runner failures, which
aren't in the coverage path).
"""
from __future__ import annotations

import importlib
import io
import sys
from contextlib import redirect_stdout, redirect_stderr
from pathlib import Path
from typing import List

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent
UTILS_DIR = REPO_ROOT / "utils"

if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))


def _discover_engines() -> List[str]:
    """Return module names (without 'utils.' prefix) for utils/*.py
    files that define a self_test function.

    Mirrors `scripts/run_engine_self_tests.py:discover_engines()` —
    keeping the discovery logic identical so the pytest wrapper and
    the standalone runner cover exactly the same set of modules.
    Drift between them would mean coverage measurements no longer
    match the runner's output.

    v10.103 note: explicit encoding="utf-8" added because v10.98's
    original used `errors="ignore"` which on Windows defaults to
    cp1252 — that combination silently dropped some bytes in some
    engine files containing UTF-8 box-drawing characters in their
    docstrings, causing the `in text` check to miss `def self_test(`
    in their actual definitions. The result: pytest collected 0
    cases on Windows, contributing nothing to coverage. With explicit
    utf-8 the discovery returns the full 152.
    """
    if not UTILS_DIR.exists():
        return []
    found: List[str] = []
    for path in sorted(UTILS_DIR.glob("*.py")):
        if path.stem.startswith("_") or path.stem == "__init__":
            continue
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        if "def self_test(" in text:
            found.append(path.stem)
    return found


# Discovery happens at collection time — pytest sees one test case
# per engine module. If the discovery list changes (e.g., new engine
# added in a future drop), pytest auto-picks it up on next run.
ENGINE_MODULES = _discover_engines()


@pytest.mark.parametrize("module_name", ENGINE_MODULES)
def test_engine_self_test(module_name: str) -> None:
    """Import utils.{module_name} and call its self_test().

    Each engine self_test is responsible for exercising its own
    contract. The pytest layer here only:
      1. Imports the module (catches import-time errors)
      2. Calls self_test() (catches contract violations)
      3. Captures stdout/stderr so passing tests don't litter pytest
         output with the engine's own ✓ messages

    On failure:
      - SystemExit (the engine's documented failure path) is caught
        and re-raised as a pytest failure with the captured stderr
        attached for diagnostics
      - Other exceptions surface unchanged (preserves the original
        traceback for stack-trace debugging)
    """
    out = io.StringIO()
    err = io.StringIO()

    try:
        with redirect_stdout(out), redirect_stderr(err):
            mod = importlib.import_module(f"utils.{module_name}")
            if not hasattr(mod, "self_test"):
                pytest.skip(
                    f"utils.{module_name} has no self_test() — "
                    f"discovery may have false-positived on a "
                    f"comment or string literal"
                )
            mod.self_test()
    except SystemExit as e:
        # The platform's engine convention: self_test() raises
        # SystemExit(1) on failure (after printing details to stderr).
        # Convert to a pytest failure with the captured detail.
        code = getattr(e, "code", 1)
        captured_err = err.getvalue().strip()
        msg = (
            f"utils.{module_name}.self_test() raised "
            f"SystemExit({code})"
        )
        if captured_err:
            msg += f"\n\nCaptured stderr:\n{captured_err}"
        pytest.fail(msg)


def test_engine_count_matches_runner_baseline() -> None:
    """Sanity check: the pytest wrapper discovers the same number
    of engines as the standalone runner. If this drifts (e.g., one
    discovers 152 and the other 153), the discovery logic in one
    has fallen out of sync.

    The expected count is intentionally NOT hardcoded — it comes
    from re-running the discovery at test time. This test catches
    only the pathological case where _discover_engines() in this
    file diverges from scripts/run_engine_self_tests.py.

    To enforce a minimum, use the assertion below.
    """
    # Import the standalone runner's discovery (same logic, but
    # we want to cross-verify by calling its function directly)
    sys.path.insert(0, str(REPO_ROOT / "scripts"))
    from run_engine_self_tests import (
        discover_engines as runner_discover
    )
    runner_engines = sorted(runner_discover())
    pytest_engines = sorted(_discover_engines())

    assert pytest_engines == runner_engines, (
        f"Discovery drift: pytest sees "
        f"{len(pytest_engines)} engines, runner sees "
        f"{len(runner_engines)}. "
        f"Diff: pytest-only="
        f"{set(pytest_engines) - set(runner_engines)}, "
        f"runner-only="
        f"{set(runner_engines) - set(pytest_engines)}"
    )


def test_minimum_engine_count() -> None:
    """Floor-check: at least 100 engines must be discovered. v10.97
    baseline is 152. A regression below 100 means a major refactor
    or accidental removal of self_test() functions.

    The floor (100) is deliberately well below the v10.97 baseline
    (152) so legitimate refactors don't fail this test
    spuriously. If engine count drops by >35%, that's the kind of
    change that warrants explicit ratification.
    """
    assert len(ENGINE_MODULES) >= 100, (
        f"Engine count {len(ENGINE_MODULES)} below floor 100. "
        f"Did self_test() functions get removed in a refactor? "
        f"v10.97 baseline was 152."
    )
