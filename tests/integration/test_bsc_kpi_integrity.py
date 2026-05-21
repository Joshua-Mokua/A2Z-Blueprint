"""
tests/integration/test_bsc_kpi_integrity.py
================================================================================
v10.298 — BSC + KPI integrity tests pinned to Phase 3.

The platform's central invariant: every performance write goes
through utils.bsc_engine, never directly to performance.* tables.
This is "user testing" in the sense that operators/auditors
depend on the BSC chokepoint working correctly.

Kaizen rationale: these tests existed in pre-Phase-3 form
(tests/test_bsc_engine.py, test_bsc_engine_breadth.py, etc.)
but they were structured around pytest fixtures that don't run
in our audit-env harness. Phase 3 needs a lean, harness-portable
smoke suite that confirms the BSC contract still holds without
needing the full pytest runtime.

These tests run AGAINST real engine functions, no mocks. They
verify:

  1. BSC engine has the 5 documented public functions
  2. validate() rejects missing required fields
  3. validate() rejects malformed period
  4. validate() rejects unknown staff_code (real users-registry
     check)
  5. submit_batch() returns structured rejection reports
  6. get_actual() returns None for unknown lookups (read-side
     contract used by every cockpit)
  7. Audit gates G8, G17, G38, G143 still report PASS for BSC
  8. No new write path bypasses BSC (regression check —
     greppable invariant)

Run: pytest tests/integration/test_bsc_kpi_integrity.py -v
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


# ============================================================
# Section 1 — BSC engine public surface
# ============================================================

def test_bsc_engine_imports():
    """utils.bsc_engine must be importable and expose the
    documented 5 functions. If this breaks, every module that
    submits BSC data breaks."""
    import utils.bsc_engine as be

    required_functions = [
        "submit", "submit_batch", "validate",
        "get_actual", "get_actuals_for_period",
    ]
    for name in required_functions:
        assert hasattr(be, name), (
            f"utils.bsc_engine.{name} missing — this is the "
            f"documented public API every BSC writer/reader "
            f"depends on"
        )


def test_bsc_engine_signatures_stable():
    """Function signatures must not drift silently. If a
    parameter is added/removed, this test should be updated
    deliberately in the same batch."""
    import inspect
    import utils.bsc_engine as be

    sig = inspect.signature(be.submit)
    params = list(sig.parameters.keys())
    expected = [
        "staff_code", "kpi_id", "value", "period",
        "source_module", "actor", "metadata",
    ]
    for p in expected:
        assert p in params, (
            f"bsc_engine.submit missing parameter `{p}`. "
            f"Documented signature: ({', '.join(expected)})"
        )


# ============================================================
# Section 2 — validate() behavior
# ============================================================

def test_validate_rejects_missing_value():
    """A record without `value` must be rejected; this is the
    most common operator error and the central data-integrity
    check."""
    from utils.bsc_engine import validate

    ok, msg = validate({
        "staff_code": "EMP001",
        "kpi_id": "K001",
        # value intentionally missing
        "period": "2026-05",
        "source_module": "test",
    })
    assert ok is False
    assert "value" in msg.lower() or "missing" in msg.lower()


def test_validate_rejects_malformed_period():
    """Period must match YYYY-MM. A "May 2026" entry would
    silently misroute analytics if accepted."""
    from utils.bsc_engine import validate

    ok, msg = validate({
        "staff_code": "EMP001",
        "kpi_id": "K001",
        "value": 50,
        "period": "May 2026",
        "source_module": "test",
    })
    assert ok is False, (
        f"Period 'May 2026' must be rejected. Got ok=True, "
        f"msg={msg!r}"
    )


def test_validate_checks_users_registry():
    """The BSC engine integrates with the users registry —
    submissions for non-existent staff_codes are rejected.
    This prevents typos from corrupting performance data."""
    from utils.bsc_engine import validate

    ok, msg = validate({
        "staff_code": "DOES_NOT_EXIST_999",
        "kpi_id": "K001",
        "value": 50,
        "period": "2026-05",
        "source_module": "test",
    })
    # Either users-registry rejection OR specific other error;
    # the important thing is rejection.
    assert ok is False


# ============================================================
# Section 3 — submit_batch contract
# ============================================================

def test_submit_batch_returns_structured_report():
    """submit_batch must report ok/rejected/created/updated/
    errors. Operator dashboards depend on this shape."""
    from utils.bsc_engine import submit_batch

    result = submit_batch(
        [
            {"staff_code": "BAD1", "kpi_id": "K001",
              "value": 10, "period": "2026-05"},
            {"staff_code": "BAD2", "kpi_id": "K001",
              "value": "not a number", "period": "2026-05"},
        ],
        source_module="test_bsc_integrity",
        actor="test_runner",
    )

    for k in ("ok", "rejected", "created", "updated", "errors"):
        assert k in result, (
            f"submit_batch result missing `{k}`. Result keys: "
            f"{sorted(result.keys())}"
        )
    # Both records should be rejected (BAD staff codes)
    assert result["rejected"] >= 2
    assert isinstance(result["errors"], list)
    assert len(result["errors"]) >= 2


def test_submit_batch_error_has_index():
    """Errors must carry the input record index so operators
    can locate the offending row in their source data."""
    from utils.bsc_engine import submit_batch

    result = submit_batch(
        [
            {"staff_code": "WONT_EXIST", "kpi_id": "K001",
              "value": 10, "period": "2026-05"},
        ],
        source_module="test_bsc_integrity",
        actor="test_runner",
    )
    assert result["errors"], "Expected at least one error entry"
    err = result["errors"][0]
    assert "index" in err, (
        f"Error entry must include `index`. Got keys: "
        f"{sorted(err.keys())}"
    )


# ============================================================
# Section 4 — get_actual / get_actuals_for_period
# ============================================================

def test_get_actual_returns_none_for_unknown():
    """Read-side contract: unknown (staff, kpi, period) returns
    None, NOT 0. Cockpits use this to differentiate "no data"
    from "zero achievement"."""
    from utils.bsc_engine import get_actual

    result = get_actual(
        "NEVER_EXISTED_999", "K_NEVER", "2026-05",
    )
    assert result is None, (
        f"Expected None for unknown lookup; got {result!r}. "
        f"If this returns 0, cockpit dashboards will "
        f"misrepresent missing data as zero performance."
    )


def test_get_actuals_for_period_returns_list():
    """get_actuals_for_period must return a list, never None or
    a dict. Operator analytics depend on iterability."""
    from utils.bsc_engine import get_actuals_for_period

    result = get_actuals_for_period(
        "2099-12",  # period that has no data
    )
    assert isinstance(result, list), (
        f"Expected list, got {type(result).__name__}: {result!r}"
    )


# ============================================================
# Section 5 — Audit gate liveness
# ============================================================

def test_bsc_audit_gates_pass():
    """The BSC-relevant audit gates must currently report PASS.
    If any of these breaks, BSC data integrity is at risk."""
    from scripts.audit import GATES

    bsc_gate_ids = {"G8", "G17", "G38", "G143"}
    bsc_results = {}
    for gid, fn in GATES:
        if gid in bsc_gate_ids:
            bsc_results[gid] = fn()

    for gid in bsc_gate_ids:
        assert gid in bsc_results, (
            f"Expected gate {gid} to exist; it's missing. "
            f"Has someone renamed/removed a BSC gate?"
        )
        result = bsc_results[gid]
        assert result["passed"], (
            f"{gid} FAILED. Summary: {result['summary']}. "
            f"Violations: {result.get('violations', [])[:3]}"
        )


# ============================================================
# Section 6 — Static invariants (no BSC bypass)
# ============================================================

def test_no_direct_performance_table_writes_outside_bsc_engine():
    """Standing rule: never write directly to `performance.*`
    tables; use the central BSC integration engine.

    Greppable invariant: only utils/bsc_engine.py may contain
    SQL inserts/updates against `performance.actuals` or
    similar. Any other file matching that pattern is a bypass
    bug.
    """
    forbidden_pattern = re.compile(
        r'(?:insert\s+into|update)\s+performance\.',
        re.IGNORECASE,
    )
    violations = []
    for path in (REPO_ROOT / "utils").glob("*.py"):
        if path.name in ("bsc_engine.py", "core_audit.py"):
            continue
        try:
            text = path.read_text()
        except Exception:
            continue
        for m in forbidden_pattern.finditer(text):
            line_no = text[:m.start()].count("\n") + 1
            violations.append(
                f"{path.name}:L{line_no}: {m.group(0)}"
            )

    # Pages directory too
    for path in (REPO_ROOT / "pages").glob("*.py"):
        try:
            text = path.read_text()
        except Exception:
            continue
        for m in forbidden_pattern.finditer(text):
            line_no = text[:m.start()].count("\n") + 1
            violations.append(
                f"pages/{path.name}:L{line_no}: {m.group(0)}"
            )

    assert not violations, (
        f"Direct performance.* writes found OUTSIDE "
        f"bsc_engine.py — these bypass the BSC chokepoint:\n  "
        + "\n  ".join(violations)
    )


def test_bsc_data_dir_exists_or_is_creatable():
    """The BSC engine writes to a data dir. If the dir is
    misconfigured the engine will silently fail. Verify the
    DATA_DIR constant points somewhere usable."""
    import utils.bsc_engine as be

    assert hasattr(be, "DATA_DIR"), "DATA_DIR constant missing"
    data_dir = Path(be.DATA_DIR)
    # Either exists, or its parent exists and we could create it
    assert data_dir.exists() or data_dir.parent.exists(), (
        f"BSC DATA_DIR {data_dir} is not creatable — neither "
        f"it nor its parent exists"
    )


# ============================================================
# Section 7 — Cockpit-BSC integration
# ============================================================

def test_cockpits_do_not_write_bsc_directly():
    """Cockpits are read-only views. None of the live cockpits
    (*_live.py) should call bsc_engine.submit() — that's the
    engines' job, not the cockpit's."""
    forbidden_calls = [
        "bsc_engine.submit(",
        "bsc_engine.submit_batch(",
    ]
    violations = []
    for page in (REPO_ROOT / "pages").glob("*_live.py"):
        text = page.read_text()
        for call in forbidden_calls:
            if call in text:
                violations.append(f"{page.name}: contains `{call}`")

    assert not violations, (
        f"Live cockpit pages calling BSC writers:\n  "
        + "\n  ".join(violations)
        + "\nCockpits are read-only; writes go through engines."
    )


# ============================================================
# Section 8 — Standards registry — BSC-tagged KPIs
# ============================================================

def test_standards_registry_loads_cleanly():
    """The standards registry feeds BSC integration. If it
    fails to load, half the platform's KPIs become invisible."""
    from utils.standards_registry import STANDARDS_REGISTRY

    # Registry is a tuple (frozen at import time per design)
    assert isinstance(STANDARDS_REGISTRY, (list, tuple))
    assert len(STANDARDS_REGISTRY) >= 300, (
        f"Standards registry has only {len(STANDARDS_REGISTRY)} "
        f"entries; expected 330+"
    )
    # All entries must have the standard_id field
    for s in STANDARDS_REGISTRY[:5]:
        assert hasattr(s, "standard_id"), (
            "Standards entry missing standard_id"
        )


# ============================================================
# Section 9 — Legacy BSC test files still present
# ============================================================
# The pre-Phase-3 BSC test suite (5 files, ~1,600 lines) uses
# pytest fixtures and classes that don't run in our audit-env
# harness — but they run in production CI with pytest installed.
# Kaizen: protect those files from accidental deletion by
# asserting their presence + substance.

LEGACY_BSC_TESTS = [
    "test_bsc_engine.py",
    "test_bsc_engine_breadth.py",
    "test_bsc_engine_closeout.py",
    "test_bsc_engine_surgical.py",
    "test_core_kpi.py",
]


def test_legacy_bsc_test_files_exist():
    """The original BSC test files must still be present.
    They're the source of truth for engine behavior under
    real pytest — production CI runs them."""
    tests_dir = REPO_ROOT / "tests"
    missing = []
    for name in LEGACY_BSC_TESTS:
        if not (tests_dir / name).exists():
            missing.append(name)
    assert not missing, (
        f"Legacy BSC/KPI test files missing: {missing}. "
        f"These predate Phase 3 but they're the comprehensive "
        f"engine test suite — production CI depends on them."
    )


def test_legacy_bsc_test_files_have_substance():
    """Each legacy file must have at least 200 lines and define
    at least one test class. If a file is gutted to a stub,
    catch it here."""
    import ast
    tests_dir = REPO_ROOT / "tests"
    too_small = []
    no_test_classes = []
    for name in LEGACY_BSC_TESTS:
        path = tests_dir / name
        if not path.exists():
            continue
        text = path.read_text()
        line_count = text.count("\n")
        if line_count < 200:
            too_small.append(f"{name} ({line_count} lines)")
        tree = ast.parse(text)
        test_classes = [
            n for n in ast.walk(tree)
            if isinstance(n, ast.ClassDef)
            and n.name.startswith("Test")
        ]
        module_test_fns = [
            n for n in ast.walk(tree)
            if isinstance(n, ast.FunctionDef)
            and n.name.startswith("test_")
        ]
        # Must have either test classes or module-level test fns
        if not test_classes and not module_test_fns:
            no_test_classes.append(name)

    assert not too_small, (
        f"Legacy BSC test files too small (likely gutted): "
        f"{too_small}"
    )
    assert not no_test_classes, (
        f"Legacy BSC test files with no test classes or "
        f"functions: {no_test_classes}"
    )
