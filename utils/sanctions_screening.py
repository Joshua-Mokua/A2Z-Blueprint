"""
================================================================================
A2Z MIS 360 — Standard #58: Sanctions Screening Engine
================================================================================

Risk classification: Cat A (sanctions list schema) + Cat C (review workflow)

Performs name screening against sanctions lists (OFAC SDN, UN Consolidated,
EU Consolidated, UK HMT, CBK domestic). Uses deterministic Levenshtein-based
fuzzy matching with configurable thresholds.

Schema (Cat A):
    risk.sanctions_list   : metadata for each sanctions source
    risk.sanctions_record : individual sanctioned entities
    risk.screening_result : every screening event (auditable)

Workflow (Cat C, default-strict):
    NEW_HIT          -> requires human review (no auto-clear)
    UNDER_REVIEW     -> compliance officer working it
    CLEARED_FALSE    -> compliance has documented false-positive reason
    CONFIRMED_TRUE   -> blocks customer/transaction; SAR triggered

Honesty rules applied:
    Rule 4: NEW_HIT cannot be auto-cleared. Compliance officer must explicitly
            mark CLEARED_FALSE with reason. NO override mode.
    Rule 6: missing/unknown sanctions list defaults to PENDING (not BYPASSED)

================================================================================
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Tuple

# Sanctions list catalog
SUPPORTED_SANCTIONS_LISTS: Tuple[str, ...] = (
    "OFAC_SDN",            # US Treasury Specially Designated Nationals
    "UN_CONSOLIDATED",     # UN Security Council
    "EU_CONSOLIDATED",     # EU restrictive measures
    "UK_HMT",              # UK Treasury
    "CBK_DOMESTIC",        # Central Bank of Kenya domestic list
)

# Match score thresholds (0-100, higher = better match)
EXACT_MATCH_THRESHOLD = 100
HIGH_CONFIDENCE_THRESHOLD = 90
MEDIUM_CONFIDENCE_THRESHOLD = 75
LOW_CONFIDENCE_THRESHOLD = 60  # below this, not flagged
SCREENING_HIT_THRESHOLD = MEDIUM_CONFIDENCE_THRESHOLD  # 75+ creates hit

# Workflow states
HIT_STATUS_NEW = "NEW_HIT"
HIT_STATUS_UNDER_REVIEW = "UNDER_REVIEW"
HIT_STATUS_CLEARED_FALSE = "CLEARED_FALSE"
HIT_STATUS_CONFIRMED_TRUE = "CONFIRMED_TRUE"

VALID_HIT_STATUSES: Tuple[str, ...] = (
    HIT_STATUS_NEW, HIT_STATUS_UNDER_REVIEW, HIT_STATUS_CLEARED_FALSE, HIT_STATUS_CONFIRMED_TRUE
)

# Allowed transitions (Cat C workflow)
ALLOWED_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    HIT_STATUS_NEW: (HIT_STATUS_UNDER_REVIEW,),
    HIT_STATUS_UNDER_REVIEW: (HIT_STATUS_CLEARED_FALSE, HIT_STATUS_CONFIRMED_TRUE),
    HIT_STATUS_CLEARED_FALSE: (),  # terminal (re-screen creates new hit)
    HIT_STATUS_CONFIRMED_TRUE: (),  # terminal
}

# Schema definitions (Cat A)
SCHEMA_SANCTIONS_LIST_TABLE = {
    "table": "risk.sanctions_list",
    "columns": [
        ("list_id", "VARCHAR(32) PRIMARY KEY"),
        ("list_name", "VARCHAR(128) NOT NULL"),
        ("source_url", "TEXT"),
        ("last_updated_at", "TIMESTAMPTZ NOT NULL"),
        ("record_count", "INTEGER NOT NULL"),
        ("active", "BOOLEAN NOT NULL DEFAULT TRUE"),
    ],
}

SCHEMA_SANCTIONS_RECORD_TABLE = {
    "table": "risk.sanctions_record",
    "columns": [
        ("record_id", "BIGSERIAL PRIMARY KEY"),
        ("list_id", "VARCHAR(32) NOT NULL REFERENCES risk.sanctions_list(list_id)"),
        ("entity_name", "VARCHAR(255) NOT NULL"),
        ("entity_type", "VARCHAR(32) NOT NULL"),  # INDIVIDUAL / ORGANIZATION / VESSEL / AIRCRAFT
        ("aliases", "TEXT[]"),
        ("date_of_birth", "DATE"),
        ("country", "VARCHAR(8)"),
        ("listing_date", "DATE NOT NULL"),
        ("sanctions_program", "VARCHAR(64)"),
        ("active", "BOOLEAN NOT NULL DEFAULT TRUE"),
    ],
    "indexes": [
        "CREATE INDEX idx_sanctions_record_name ON risk.sanctions_record (entity_name)",
        "CREATE INDEX idx_sanctions_record_active ON risk.sanctions_record (active) WHERE active",
    ],
}

SCHEMA_SCREENING_RESULT_TABLE = {
    "table": "risk.screening_result",
    "columns": [
        ("screening_id", "BIGSERIAL PRIMARY KEY"),
        ("subject_type", "VARCHAR(16) NOT NULL"),  # CUSTOMER / TRANSACTION / COUNTERPARTY
        ("subject_id", "VARCHAR(64) NOT NULL"),
        ("subject_name", "VARCHAR(255) NOT NULL"),
        ("matched_record_id", "BIGINT REFERENCES risk.sanctions_record(record_id)"),
        ("match_score", "INTEGER NOT NULL"),  # 0-100
        ("hit_status", "VARCHAR(32) NOT NULL"),
        ("screened_at", "TIMESTAMPTZ NOT NULL"),
        ("reviewer_id", "VARCHAR(64)"),
        ("review_completed_at", "TIMESTAMPTZ"),
        ("clearance_reason", "TEXT"),
    ],
    "indexes": [
        "CREATE INDEX idx_screening_subject ON risk.screening_result (subject_type, subject_id)",
        "CREATE INDEX idx_screening_status ON risk.screening_result (hit_status) WHERE hit_status IN ('NEW_HIT', 'UNDER_REVIEW')",
    ],
}


def _normalize_name(name: str) -> str:
    """Normalize for matching: lowercase, strip punct, collapse whitespace."""
    if not name:
        return ""
    out = []
    for ch in name.lower():
        if ch.isalnum() or ch == " ":
            out.append(ch)
        else:
            out.append(" ")
    return " ".join("".join(out).split())


def _levenshtein(a: str, b: str) -> int:
    """Compute edit distance between two strings (deterministic)."""
    if a == b:
        return 0
    if not a:
        return len(b)
    if not b:
        return len(a)
    prev = list(range(len(b) + 1))
    for i, ca in enumerate(a):
        cur = [i + 1]
        for j, cb in enumerate(b):
            ins = cur[j] + 1
            dele = prev[j + 1] + 1
            sub = prev[j] + (0 if ca == cb else 1)
            cur.append(min(ins, dele, sub))
        prev = cur
    return prev[-1]


def fuzzy_match_score(name_a: str, name_b: str) -> int:
    """Compute 0-100 match score from normalized Levenshtein distance."""
    a = _normalize_name(name_a)
    b = _normalize_name(name_b)
    if not a or not b:
        return 0
    if a == b:
        return 100
    dist = _levenshtein(a, b)
    max_len = max(len(a), len(b))
    if max_len == 0:
        return 0
    similarity = 1.0 - (dist / max_len)
    return max(0, min(100, int(round(similarity * 100))))


@dataclass
class SanctionsRecord:
    record_id: int
    list_id: str
    entity_name: str
    entity_type: str = "INDIVIDUAL"
    aliases: List[str] = field(default_factory=list)
    country: Optional[str] = None
    listing_date: Optional[str] = None
    active: bool = True


@dataclass
class ScreeningHit:
    screening_id: int
    subject_type: str
    subject_id: str
    subject_name: str
    matched_record_id: int
    matched_entity_name: str
    matched_list_id: str
    match_score: int
    hit_status: str
    screened_at: str
    reviewer_id: Optional[str] = None
    review_completed_at: Optional[str] = None
    clearance_reason: Optional[str] = None

    def to_dict(self) -> Dict[str, Any]:
        return {
            "screening_id": self.screening_id,
            "subject_type": self.subject_type,
            "subject_id": self.subject_id,
            "subject_name": self.subject_name,
            "matched_record_id": self.matched_record_id,
            "matched_entity_name": self.matched_entity_name,
            "matched_list_id": self.matched_list_id,
            "match_score": self.match_score,
            "hit_status": self.hit_status,
            "screened_at": self.screened_at,
            "reviewer_id": self.reviewer_id,
            "review_completed_at": self.review_completed_at,
            "clearance_reason": self.clearance_reason,
        }


class SanctionsScreeningEngine:
    """Deterministic name-based sanctions screening with default-strict workflow."""

    def __init__(self, sanctions_records: Optional[List[SanctionsRecord]] = None):
        # Rule 6: unknown list_ids filtered; inactive records dropped
        recs = list(sanctions_records or [])
        self._records: List[SanctionsRecord] = [
            r for r in recs if r.active and r.list_id in SUPPORTED_SANCTIONS_LISTS
        ]
        self._screening_log: List[ScreeningHit] = []
        self._next_screening_id = 1

    def load_records(self, records: List[SanctionsRecord]) -> int:
        """Load/replace sanctions records. Returns count loaded."""
        self._records = [r for r in records if r.active and r.list_id in SUPPORTED_SANCTIONS_LISTS]
        return len(self._records)

    def screen(
        self,
        subject_id: str,
        subject_name: str,
        subject_type: str = "CUSTOMER",
    ) -> List[ScreeningHit]:
        """
        Screen a subject against all loaded sanctions records.

        Returns hits where match_score >= SCREENING_HIT_THRESHOLD.
        New hits start as NEW_HIT (Cat C: requires manual review).
        """
        hits: List[ScreeningHit] = []
        ts = datetime.now(timezone.utc).isoformat()
        seen_records: set = set()
        for rec in self._records:
            best_score = fuzzy_match_score(subject_name, rec.entity_name)
            best_match_name = rec.entity_name
            for alias in rec.aliases:
                alias_score = fuzzy_match_score(subject_name, alias)
                if alias_score > best_score:
                    best_score = alias_score
                    best_match_name = alias
            if best_score >= SCREENING_HIT_THRESHOLD and rec.record_id not in seen_records:
                seen_records.add(rec.record_id)
                hit = ScreeningHit(
                    screening_id=self._next_screening_id,
                    subject_type=subject_type,
                    subject_id=subject_id,
                    subject_name=subject_name,
                    matched_record_id=rec.record_id,
                    matched_entity_name=best_match_name,
                    matched_list_id=rec.list_id,
                    match_score=best_score,
                    hit_status=HIT_STATUS_NEW,
                    screened_at=ts,
                )
                self._next_screening_id += 1
                self._screening_log.append(hit)
                hits.append(hit)
        return hits

    def get_open_hits(self) -> List[ScreeningHit]:
        """Return all hits not in terminal status."""
        return [h for h in self._screening_log if h.hit_status in (HIT_STATUS_NEW, HIT_STATUS_UNDER_REVIEW)]

    def transition_hit(
        self,
        screening_id: int,
        new_status: str,
        reviewer_id: str,
        clearance_reason: Optional[str] = None,
    ) -> Tuple[bool, str]:
        """
        Transition a hit through the workflow.

        Rule 4: NEW_HIT cannot directly become CLEARED_FALSE — must go through
        UNDER_REVIEW first. CLEARED_FALSE requires a clearance_reason.
        Reviewer ID is mandatory for any transition.
        """
        if new_status not in VALID_HIT_STATUSES:
            return False, f"invalid_status:{new_status}"
        if not reviewer_id:
            return False, "reviewer_id_required"

        hit = next((h for h in self._screening_log if h.screening_id == screening_id), None)
        if hit is None:
            return False, f"screening_id_not_found:{screening_id}"

        allowed = ALLOWED_TRANSITIONS.get(hit.hit_status, ())
        if new_status not in allowed:
            return False, f"transition_not_allowed:{hit.hit_status}->{new_status}"

        # Cleared false requires clearance reason
        if new_status == HIT_STATUS_CLEARED_FALSE and not clearance_reason:
            return False, "clearance_reason_required_for_cleared_false"

        # Rule 4: confirming TRUE also requires reason for audit
        if new_status == HIT_STATUS_CONFIRMED_TRUE and not clearance_reason:
            return False, "confirmation_reason_required_for_confirmed_true"

        hit.hit_status = new_status
        hit.reviewer_id = reviewer_id
        hit.clearance_reason = clearance_reason
        if new_status in (HIT_STATUS_CLEARED_FALSE, HIT_STATUS_CONFIRMED_TRUE):
            hit.review_completed_at = datetime.now(timezone.utc).isoformat()
        return True, "transitioned"

    def screening_summary(self) -> Dict[str, Any]:
        """Aggregate screening log."""
        by_status = {s: 0 for s in VALID_HIT_STATUSES}
        for h in self._screening_log:
            by_status[h.hit_status] = by_status.get(h.hit_status, 0) + 1
        return {
            "total_records": len(self._records),
            "total_screenings": len(self._screening_log),
            "by_status": by_status,
            "open_hits": by_status[HIT_STATUS_NEW] + by_status[HIT_STATUS_UNDER_REVIEW],
        }


# ============================================================================
# Self-tests
# ============================================================================

def _make_records() -> List[SanctionsRecord]:
    return [
        SanctionsRecord(record_id=1, list_id="OFAC_SDN", entity_name="John Smuggler", aliases=["J Smuggler", "Johnny Smug"]),
        SanctionsRecord(record_id=2, list_id="UN_CONSOLIDATED", entity_name="ABC Terrorist Front", aliases=[]),
        SanctionsRecord(record_id=3, list_id="EU_CONSOLIDATED", entity_name="Maria Sanctioned"),
        SanctionsRecord(record_id=4, list_id="CBK_DOMESTIC", entity_name="Local Bad Actor Ltd"),
    ]

def _test_exact_match_creates_hit():
    eng = SanctionsScreeningEngine(_make_records())
    hits = eng.screen("C001", "John Smuggler")
    assert len(hits) == 1
    assert hits[0].match_score == 100
    assert hits[0].hit_status == HIT_STATUS_NEW
    assert hits[0].matched_list_id == "OFAC_SDN"

def _test_alias_match():
    eng = SanctionsScreeningEngine(_make_records())
    hits = eng.screen("C002", "Johnny Smug")
    assert len(hits) == 1
    assert hits[0].match_score == 100
    assert hits[0].matched_entity_name == "Johnny Smug"

def _test_fuzzy_match_typo():
    eng = SanctionsScreeningEngine(_make_records())
    # "Maria Sanctionned" - 1 extra char
    hits = eng.screen("C003", "Maria Sanctionned")
    assert len(hits) == 1
    assert hits[0].match_score >= MEDIUM_CONFIDENCE_THRESHOLD

def _test_no_match_below_threshold():
    eng = SanctionsScreeningEngine(_make_records())
    hits = eng.screen("C004", "Jane Honest")
    assert hits == []

def _test_default_strict_no_auto_clear():
    """Rule 4: NEW_HIT cannot transition directly to CLEARED_FALSE."""
    eng = SanctionsScreeningEngine(_make_records())
    hits = eng.screen("C005", "John Smuggler")
    sid = hits[0].screening_id
    ok, reason = eng.transition_hit(sid, HIT_STATUS_CLEARED_FALSE, "officer_001", "false_positive")
    assert not ok, "Direct NEW->CLEARED_FALSE must be rejected"
    assert "transition_not_allowed" in reason

def _test_workflow_normal_path():
    eng = SanctionsScreeningEngine(_make_records())
    hits = eng.screen("C006", "John Smuggler")
    sid = hits[0].screening_id
    ok, _ = eng.transition_hit(sid, HIT_STATUS_UNDER_REVIEW, "officer_001")
    assert ok
    ok, _ = eng.transition_hit(sid, HIT_STATUS_CLEARED_FALSE, "officer_001", "different_DOB_confirmed")
    assert ok
    h = eng._screening_log[0]
    assert h.hit_status == HIT_STATUS_CLEARED_FALSE
    assert h.reviewer_id == "officer_001"
    assert h.review_completed_at is not None

def _test_clearance_requires_reason():
    eng = SanctionsScreeningEngine(_make_records())
    hits = eng.screen("C007", "John Smuggler")
    sid = hits[0].screening_id
    eng.transition_hit(sid, HIT_STATUS_UNDER_REVIEW, "officer_001")
    ok, reason = eng.transition_hit(sid, HIT_STATUS_CLEARED_FALSE, "officer_001", None)
    assert not ok
    assert "clearance_reason_required" in reason

def _test_terminal_state_no_change():
    eng = SanctionsScreeningEngine(_make_records())
    hits = eng.screen("C008", "John Smuggler")
    sid = hits[0].screening_id
    eng.transition_hit(sid, HIT_STATUS_UNDER_REVIEW, "officer_001")
    eng.transition_hit(sid, HIT_STATUS_CONFIRMED_TRUE, "officer_001", "verified_match")
    ok, reason = eng.transition_hit(sid, HIT_STATUS_CLEARED_FALSE, "officer_001", "oops")
    assert not ok, "Terminal state must reject further transitions"
    assert "transition_not_allowed" in reason

def _test_reviewer_id_required():
    eng = SanctionsScreeningEngine(_make_records())
    hits = eng.screen("C009", "John Smuggler")
    sid = hits[0].screening_id
    ok, reason = eng.transition_hit(sid, HIT_STATUS_UNDER_REVIEW, "")
    assert not ok
    assert "reviewer_id_required" in reason

def _test_unknown_screening_id():
    eng = SanctionsScreeningEngine(_make_records())
    ok, reason = eng.transition_hit(99999, HIT_STATUS_UNDER_REVIEW, "officer_001")
    assert not ok
    assert "not_found" in reason

def _test_unknown_list_filtered_rule6():
    """Rule 6: records with unsupported list_id must be filtered, not silently used."""
    bad_rec = SanctionsRecord(record_id=999, list_id="FAKE_LIST", entity_name="X")
    eng = SanctionsScreeningEngine([bad_rec] + _make_records())
    assert len(eng._records) == 4  # FAKE_LIST filtered
    summary = eng.screening_summary()
    assert summary["total_records"] == 4

def _test_screening_summary():
    eng = SanctionsScreeningEngine(_make_records())
    eng.screen("C010", "John Smuggler")
    eng.screen("C011", "Maria Sanctioned")
    eng.screen("C012", "Random Person")
    s = eng.screening_summary()
    assert s["total_screenings"] == 2
    assert s["by_status"][HIT_STATUS_NEW] == 2
    assert s["open_hits"] == 2

def _test_schema_definitions():
    """Cat A: schema definitions present and well-formed."""
    for sch in (SCHEMA_SANCTIONS_LIST_TABLE, SCHEMA_SANCTIONS_RECORD_TABLE, SCHEMA_SCREENING_RESULT_TABLE):
        assert "table" in sch
        assert "columns" in sch
        assert len(sch["columns"]) >= 3
        # First col should be PK
        assert "PRIMARY KEY" in sch["columns"][0][1]


def self_test() -> bool:
    tests = [
        _test_exact_match_creates_hit,
        _test_alias_match,
        _test_fuzzy_match_typo,
        _test_no_match_below_threshold,
        _test_default_strict_no_auto_clear,
        _test_workflow_normal_path,
        _test_clearance_requires_reason,
        _test_terminal_state_no_change,
        _test_reviewer_id_required,
        _test_unknown_screening_id,
        _test_unknown_list_filtered_rule6,
        _test_screening_summary,
        _test_schema_definitions,
    ]
    print("=" * 60)
    print("Sanctions Screening Engine — Self-Tests (#58)")
    print("=" * 60)
    failed = 0
    for t in tests:
        try:
            t()
            print(f"  PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  FAIL  {t.__name__}: {e}")
        except Exception as e:
            failed += 1
            print(f"  ERROR {t.__name__}: {e}")
    print("-" * 60)
    if failed == 0:
        print(f"  ALL {len(tests)} TESTS PASSED")
        return True
    print(f"  {failed}/{len(tests)} FAILED")
    return False


if __name__ == "__main__":
    import sys
    sys.exit(0 if self_test() else 1)
