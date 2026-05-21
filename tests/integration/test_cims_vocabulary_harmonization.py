"""
tests/integration/test_cims_vocabulary_harmonization.py
================================================================================
v10.303 — CIMS vocabulary harmonization (B-001 closure).

Backlog item B-001 was logged in v10.295: different CIMS
engines use different field names and instruction-type
vocabularies for the same semantic concept. A `COMPLAINT`
captured at #166 won't match SLA's `CUSTOMER_COMPLAINT`
deadline key at #171, so SLA obligations don't auto-attach to
captured instructions in real-world data.

Per the backlog plan, we add a TRANSLATION LAYER in
utils/cockpit_read.py rather than rewriting engine enums
(rewrites would break the byte-for-byte G182-G185 locks).

This batch ships:
  - normalize_instruction_type(raw) — canonical mapper
  - cims_instruction_trace enriched with the canonical name
    alongside the original
  - cims_vocabulary_map() — operator-facing reference
  - documented mapping (capture/NLP → SLA framework names)

Test sections:
  1. normalize_instruction_type contract (basic mappings)
  2. Canonical names match SLA framework keys
  3. Round-trip + idempotency
  4. Unknown values pass through (legacy tolerance)
  5. Case-insensitive matching
  6. cims_vocabulary_map() shape
  7. cims_instruction_trace exposes canonical_instruction_type
  8. Audit gate G194 liveness
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest


REPO_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.insert(0, str(REPO_ROOT))


# ============================================================
# Section 1 — normalize_instruction_type basic mappings
# ============================================================

def test_normalize_complaint_maps_to_customer_complaint():
    """Capture writes `COMPLAINT`; SLA's deadline dict keys on
    `CUSTOMER_COMPLAINT`. Without normalisation the dispute
    deadline never attaches."""
    from utils.cockpit_read import normalize_instruction_type
    assert normalize_instruction_type("COMPLAINT") == (
        "CUSTOMER_COMPLAINT"
    )


def test_normalize_information_request_maps_to_general_inquiry():
    """NLP #167 emits `INFORMATION_REQUEST`; SLA + capture both
    use `GENERAL_INQUIRY` as the canonical key."""
    from utils.cockpit_read import normalize_instruction_type
    assert normalize_instruction_type("INFORMATION_REQUEST") == (
        "GENERAL_INQUIRY"
    )


def test_normalize_passthrough_already_canonical():
    """Values already in canonical form (SLA's vocabulary)
    must pass through unchanged."""
    from utils.cockpit_read import normalize_instruction_type
    for canonical in (
        "DISPUTE_INVESTIGATION",
        "BILLING_ERROR",
        "CUSTOMER_COMPLAINT",
        "GENERAL_INQUIRY",
        "REGULATORY_REPORTING",
    ):
        assert normalize_instruction_type(canonical) == canonical


# ============================================================
# Section 2 — Canonical targets match SLA framework
# ============================================================

def test_all_normalised_values_exist_in_sla_deadlines():
    """Every value normalise() returns (except passthrough
    for unknowns) must be a key in cims_regulatory_sla's
    INSTRUCTION_TYPE_DEFAULT_DEADLINES_HOURS dict — that's the
    point of the harmonisation."""
    from utils.cockpit_read import normalize_instruction_type
    from utils.cims_regulatory_sla import (
        INSTRUCTION_TYPE_DEFAULT_DEADLINES_HOURS,
    )
    sla_keys = set(INSTRUCTION_TYPE_DEFAULT_DEADLINES_HOURS)

    # Every documented capture/NLP value must normalise to a
    # key that the SLA framework actually has a deadline for.
    from utils.cims_omnichannel_capture import INSTRUCTION_TYPES
    for raw in INSTRUCTION_TYPES:
        norm = normalize_instruction_type(raw)
        # If we mapped it to a non-passthrough, the target must
        # exist in SLA framework
        if norm != raw:
            assert norm in sla_keys, (
                f"normalize_instruction_type({raw!r}) → "
                f"{norm!r} which is NOT a key in SLA's "
                f"INSTRUCTION_TYPE_DEFAULT_DEADLINES_HOURS. "
                f"Mapping must target real SLA keys."
            )


# ============================================================
# Section 3 — Idempotency / round-trip
# ============================================================

def test_normalize_is_idempotent():
    """Calling normalise twice must return the same value."""
    from utils.cockpit_read import normalize_instruction_type
    for raw in (
        "COMPLAINT", "INFORMATION_REQUEST", "ACCOUNT_OPENING",
        "STATEMENT_REQUEST", "DISPUTE_INVESTIGATION",
        "BILLING_ERROR", "CUSTOMER_COMPLAINT",
        "GENERAL_INQUIRY", "REGULATORY_REPORTING",
    ):
        once = normalize_instruction_type(raw)
        twice = normalize_instruction_type(once)
        assert once == twice, (
            f"normalise not idempotent for {raw!r}: "
            f"once={once!r}, twice={twice!r}"
        )


# ============================================================
# Section 4 — Unknown values pass through
# ============================================================

def test_normalize_unknown_passes_through():
    """Real-world data may have legacy / typo / vendor-specific
    instruction types we haven't mapped. They must pass through
    unchanged rather than crash or return None — cockpit can
    still display them, operators can investigate."""
    from utils.cockpit_read import normalize_instruction_type
    for unknown in (
        "WIDGET_THINGY",
        "vendor_xyz_legacy_2018",
        "Some Free-form Field",
    ):
        result = normalize_instruction_type(unknown)
        assert result == unknown, (
            f"unknown value {unknown!r} should pass through; "
            f"got {result!r}"
        )


def test_normalize_handles_none_and_empty():
    """None and empty must not crash; return the input as a
    string (or empty string for None)."""
    from utils.cockpit_read import normalize_instruction_type
    # None → empty string (or stays None — either is safe)
    result = normalize_instruction_type(None)
    assert result in (None, "", "UNKNOWN"), (
        f"None input should produce safe value; got {result!r}"
    )
    assert normalize_instruction_type("") in ("", "UNKNOWN")


# ============================================================
# Section 5 — Case-insensitive matching
# ============================================================

def test_normalize_is_case_insensitive_for_known_values():
    """Operators / legacy data may have lowercase variants.
    Map them to the canonical UPPER_CASE form."""
    from utils.cockpit_read import normalize_instruction_type
    assert normalize_instruction_type("complaint") == (
        "CUSTOMER_COMPLAINT"
    )
    assert normalize_instruction_type("Complaint") == (
        "CUSTOMER_COMPLAINT"
    )
    assert normalize_instruction_type("information_request") == (
        "GENERAL_INQUIRY"
    )


# ============================================================
# Section 6 — cims_vocabulary_map operator-facing reference
# ============================================================

def test_cims_vocabulary_map_exists():
    """A separate function exposes the full mapping so operators
    + the React SPA can render a reference table."""
    from utils.cockpit_read import cims_vocabulary_map
    m = cims_vocabulary_map()
    assert isinstance(m, dict)


def test_cims_vocabulary_map_has_documented_structure():
    """The map must group by source vocabulary so the operator
    can scan it: e.g. {capture: {COMPLAINT: CUSTOMER_COMPLAINT,
    ...}, nlp: {...}, ...}."""
    from utils.cockpit_read import cims_vocabulary_map
    m = cims_vocabulary_map()
    # At minimum must have a 'capture' and 'nlp' group
    assert "capture" in m
    assert "nlp" in m
    # And canonical SLA keys reference
    assert "canonical" in m
    # capture group has COMPLAINT entry
    assert m["capture"].get("COMPLAINT") == "CUSTOMER_COMPLAINT"
    # nlp group has INFORMATION_REQUEST entry
    assert m["nlp"].get("INFORMATION_REQUEST") == (
        "GENERAL_INQUIRY"
    )


# ============================================================
# Section 7 — cims_instruction_trace enriched
# ============================================================

def test_cims_instruction_trace_includes_canonical_field(
    tmp_path,
):
    """When the trace returns a capture record with an
    instruction_type, it must also include the
    canonical_instruction_type so React + operators can join
    against SLA deadlines."""
    import json
    from utils.cockpit_read import cims_instruction_trace

    # Build minimal synthetic data
    sessions = [
        {
            "session_id": "SESS-VOCAB-1",
            "instruction_type": "COMPLAINT",
            "originating_channel": "MOBILE_APP",
        }
    ]
    (tmp_path / "cims_capture_sessions.json").write_text(
        json.dumps(sessions))

    result = cims_instruction_trace(
        "SESS-VOCAB-1", data_dir=tmp_path,
    )
    assert result["capture"] is not None
    cap = result["capture"]
    assert cap.get("canonical_instruction_type") == (
        "CUSTOMER_COMPLAINT"
    ), (
        f"trace must enrich capture with canonical_instruction_"
        f"type; got {cap.get('canonical_instruction_type')!r}"
    )
    # Original field preserved
    assert cap.get("instruction_type") == "COMPLAINT"


def test_cims_instruction_trace_unknown_session_doesnt_crash(
    tmp_path,
):
    """The enrichment must not break the existing well-formed-
    empty-trace contract for unknown sessions."""
    from utils.cockpit_read import cims_instruction_trace
    result = cims_instruction_trace(
        "DOES-NOT-EXIST", data_dir=tmp_path,
    )
    assert result["capture"] is None


# ============================================================
# Section 8 — Audit gate G194
# ============================================================

def test_g194_gate_exists_and_passes():
    """G194 must report PASS after vocab harmonisation."""
    from scripts.audit import GATES
    g194 = None
    for gid, fn in GATES:
        if gid == "G194":
            g194 = fn()
            break
    assert g194 is not None, "G194 gate not registered"
    assert g194["passed"], (
        f"G194 failed. Summary: {g194.get('summary', '')}. "
        f"Violations: {g194.get('violations', [])[:5]}"
    )
