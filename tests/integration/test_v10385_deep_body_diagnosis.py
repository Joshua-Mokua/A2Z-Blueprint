"""Integration tests for v10.385 — Deep Body-Wide Diagnosis.

Phase B closes with a comprehensive body-wide health survey of all 7
organs. REVIEW ONLY batch — no code changes.

9 tests across 3 sections.
"""

import sys
from pathlib import Path

REPO = Path("/tmp/a2z_fix")
if str(REPO) not in sys.path:
    sys.path.insert(0, str(REPO))


def _reimport(prefix):
    for k in list(sys.modules):
        if k.startswith(prefix):
            del sys.modules[k]


# ────────────────────────────────────────────────────────────────────
# Section 1 — Diagnosis document structure
# ────────────────────────────────────────────────────────────────────

def test_v10385_diagnosis_present_and_substantial():
    p = REPO / "docs" / "DEEP_BODY_DIAGNOSIS_v10.385.md"
    assert p.exists()
    assert p.stat().st_size > 15000, (
        f"diagnosis too small ({p.stat().st_size}B) — should be 15KB+"
    )


def test_v10385_diagnosis_has_13_parts():
    p = REPO / "docs" / "DEEP_BODY_DIAGNOSIS_v10.385.md"
    text = p.read_text()
    for part in range(1, 14):
        assert f"## Part {part}" in text, f"missing Part {part}"


def test_v10385_diagnosis_covers_all_7_organs():
    p = REPO / "docs" / "DEEP_BODY_DIAGNOSIS_v10.385.md"
    text = p.read_text()
    for organ in ("Skeleton", "Circulatory", "Nervous", "Recognition",
                  "Endocrine", "Brain", "Prioritization"):
        assert organ in text, f"organ {organ} not covered"


# ────────────────────────────────────────────────────────────────────
# Section 2 — Content coverage (findings + fix sequence)
# ────────────────────────────────────────────────────────────────────

def test_v10385_diagnosis_catalogs_findings_per_organ():
    """Each organ should have at least one Finding with prefix."""
    p = REPO / "docs" / "DEEP_BODY_DIAGNOSIS_v10.385.md"
    text = p.read_text()
    for prefix in ("Finding S", "Finding C", "Finding N",
                   "Finding R", "Finding E", "Finding B", "Finding P"):
        assert prefix in text, f"missing findings with prefix {prefix!r}"


def test_v10385_diagnosis_has_4_tier_fix_sequence():
    p = REPO / "docs" / "DEEP_BODY_DIAGNOSIS_v10.385.md"
    text = p.read_text()
    for tier in ("Tier-1", "Tier-2", "Tier-3", "Tier-4"):
        assert tier in text, f"missing {tier} fix sequence"


def test_v10385_diagnosis_includes_batch_numbers():
    """Fix sequence should reference v10.386 through v10.410."""
    p = REPO / "docs" / "DEEP_BODY_DIAGNOSIS_v10.385.md"
    text = p.read_text()
    for batch in ("v10.386", "v10.390", "v10.400", "v10.410"):
        assert batch in text, f"diagnosis missing batch reference {batch}"


def test_v10385_diagnosis_body_system_framing():
    p = REPO / "docs" / "DEEP_BODY_DIAGNOSIS_v10.385.md"
    text = p.read_text().lower()
    # Should be heavily organ-framed
    assert text.count("organ") > 10, "diagnosis under-uses 'organ'"
    assert text.count("body") > 10, "diagnosis under-uses 'body'"


# ────────────────────────────────────────────────────────────────────
# Section 3 — G271 + read-only invariant + no regression
# ────────────────────────────────────────────────────────────────────

def test_v10385_g271_passes():
    sys.path.insert(0, str(REPO / "scripts"))
    _reimport("audit")
    from audit import gate_v10385_body_diagnosis
    r = gate_v10385_body_diagnosis()
    assert r["passed"], r.get("violations")
    assert r["id"] == "G271"


def test_v10385_is_review_only_no_code_changes():
    """v10.385 should ship REVIEW DOCS ONLY — no v10385 implementation
    markers in utils/."""
    for mod in (REPO / "utils").glob("*.py"):
        text = mod.read_text()
        for line in text.split("\n"):
            stripped = line.strip()
            if stripped.startswith("def ") or stripped.startswith("class "):
                assert "v10385" not in stripped, (
                    f"v10.385 should be review-only but found "
                    f"implementation in {mod.name}: {stripped}"
                )
