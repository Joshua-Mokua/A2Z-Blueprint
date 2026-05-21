"""
================================================================================
A2Z MIS 360 — Standard #172: Secure Document & PAN Management
================================================================================

Risk classification: Cat C (registry of tokenised PAN handles +
document vault references; never stores raw PAN, never stores raw
document bytes; reads from upstream tokenisation/vault systems).

Subcategory: cims

Tokenised PAN storage with secure document vault. Composes upstream
capture (#166), STP (#168), and identity (#173) — registers PAN
tokens (NEVER raw PANs) and document vault references that other
CIMS engines reference by handle. Never decrypts, never stores raw
data; PCI DSS scope is delegated to the tokenisation provider.

CRITICAL: The engine REJECTS any field that looks like a raw PAN
(13-19 digit numeric string with valid Luhn). It only accepts:
  • Token strings produced by the tokenisation provider
  • Last-4 digits (always allowed under PCI DSS)
  • PAN BIN (first 6, allowed under PCI DSS)

Public API:
    register_token(token_data, actor, reason)
    transition_token_state(token_id, new_state, actor, reason)
    register_document(doc_data, actor, reason)
    transition_document_state(doc_id, new_state, actor, reason)
    record_access_event(event_data, actor)
    pan_inventory_summary() -> Dict
    document_inventory_summary() -> Dict

PAN_TOKEN_STATES byte-for-byte (4):
    ACTIVE, REVOKED, EXPIRED, ARCHIVED

ALLOWED_TOKEN_TRANSITIONS (Rule 4):
    ACTIVE   → REVOKED | EXPIRED | ARCHIVED
    REVOKED  → ARCHIVED
    EXPIRED  → ARCHIVED
    ARCHIVED → ()

DOCUMENT_STATES byte-for-byte (5):
    UPLOADED, IN_REVIEW, VERIFIED, REJECTED, ARCHIVED

ALLOWED_DOCUMENT_TRANSITIONS (Rule 4):
    UPLOADED  → IN_REVIEW | REJECTED | ARCHIVED
    IN_REVIEW → VERIFIED | REJECTED | ARCHIVED
    VERIFIED  → ARCHIVED
    REJECTED  → ARCHIVED
    ARCHIVED  → ()

DOCUMENT_TYPES byte-for-byte (8):
    NATIONAL_ID, PASSPORT, KRA_PIN_CERTIFICATE, UTILITY_BILL,
    BANK_STATEMENT, BUSINESS_REGISTRATION, PROOF_OF_INCOME, OTHER

ACCESS_EVENT_TYPES byte-for-byte (5):
    TOKEN_LOOKUP, DOCUMENT_VIEW, DOCUMENT_DOWNLOAD,
    METADATA_UPDATE, ACCESS_DENIED

PAN_FIELD_KINDS byte-for-byte (3):
    TOKEN, LAST_FOUR, BIN

DEFAULT_TOKEN_TTL_DAYS = 365
DEFAULT_DOCUMENT_RETENTION_YEARS = 7
PCI_DSS_RAW_PAN_PROHIBITED = True

================================================================================
"""

from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple


PAN_TOKEN_STATES: Tuple[str, ...] = (
    "ACTIVE", "REVOKED", "EXPIRED", "ARCHIVED",
)

ALLOWED_TOKEN_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "ACTIVE":   ("REVOKED", "EXPIRED", "ARCHIVED"),
    "REVOKED":  ("ARCHIVED",),
    "EXPIRED":  ("ARCHIVED",),
    "ARCHIVED": (),
}

DOCUMENT_STATES: Tuple[str, ...] = (
    "UPLOADED", "IN_REVIEW", "VERIFIED", "REJECTED", "ARCHIVED",
)

ALLOWED_DOCUMENT_TRANSITIONS: Dict[str, Tuple[str, ...]] = {
    "UPLOADED":  ("IN_REVIEW", "REJECTED", "ARCHIVED"),
    "IN_REVIEW": ("VERIFIED", "REJECTED", "ARCHIVED"),
    "VERIFIED":  ("ARCHIVED",),
    "REJECTED":  ("ARCHIVED",),
    "ARCHIVED":  (),
}

DOCUMENT_TYPES: Tuple[str, ...] = (
    "NATIONAL_ID", "PASSPORT", "KRA_PIN_CERTIFICATE",
    "UTILITY_BILL", "BANK_STATEMENT", "BUSINESS_REGISTRATION",
    "PROOF_OF_INCOME", "OTHER",
)

ACCESS_EVENT_TYPES: Tuple[str, ...] = (
    "TOKEN_LOOKUP", "DOCUMENT_VIEW", "DOCUMENT_DOWNLOAD",
    "METADATA_UPDATE", "ACCESS_DENIED",
)

PAN_FIELD_KINDS: Tuple[str, ...] = (
    "TOKEN", "LAST_FOUR", "BIN",
)

DEFAULT_TOKEN_TTL_DAYS = 365
DEFAULT_DOCUMENT_RETENTION_YEARS = 7
PCI_DSS_RAW_PAN_PROHIBITED = True


def _luhn_check(digits: str) -> bool:
    """Standard Luhn algorithm — returns True if `digits` is a valid PAN."""
    if not digits.isdigit() or len(digits) < 13 or len(digits) > 19:
        return False
    total = 0
    reverse = digits[::-1]
    for i, ch in enumerate(reverse):
        d = int(ch)
        if i % 2 == 1:
            d *= 2
            if d > 9:
                d -= 9
        total += d
    return total % 10 == 0


def _looks_like_raw_pan(value: Any) -> bool:
    """Reject any string that looks like a raw PAN — including
    PANs embedded in larger narrative text (e.g. spaces, dashes,
    or other non-digit separators within or around the digit run).
    """
    if not isinstance(value, str):
        return False
    # Strip common PAN separators (space, dash) anywhere in the string.
    cleaned = value.replace(" ", "").replace("-", "")
    # Direct match: cleaned is a pure digit run of PAN length
    if cleaned.isdigit() and 13 <= len(cleaned) <= 19:
        return _luhn_check(cleaned)
    # Scan for any contiguous digit run of PAN length with a valid
    # Luhn — covers raw PANs embedded inside text/narrative.
    import re as _re
    for match in _re.finditer(r"\d{13,19}", cleaned):
        if _luhn_check(match.group()):
            return True
    return False


class SecurePANDocumentEngine:
    """Tokenised PAN + document vault registry. Never stores raw PAN."""

    def __init__(
        self,
        tokens_path: Optional[Path] = None,
        documents_path: Optional[Path] = None,
        access_events_path: Optional[Path] = None,
    ):
        base = Path(__file__).parent.parent / "data"
        self.tokens_path = (
            tokens_path or base / "cims_pan_tokens.json"
        )
        self.documents_path = (
            documents_path or base / "cims_documents.json"
        )
        self.access_events_path = (
            access_events_path or base / "cims_pan_access_events.json"
        )

    def _load(self, path: Path, table: str, idx: Tuple[str, ...]) -> List[Dict[str, Any]]:
        try:
            from utils.db import db as _db
            data = _db.dual_load(path, table=table, index_cols=idx)
            return data if isinstance(data, list) else []
        except Exception:
            return []

    def _save(self, path: Path, records: List[Dict[str, Any]],
                table: str, pk: str) -> bool:
        try:
            from utils.db import db as _db
            path.parent.mkdir(parents=True, exist_ok=True)
            _db.dual_save(path, data=records, table=table, pk_col=pk)
            return True
        except Exception:
            return False

    def register_token(
        self, token_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("token_id", "token_value", "kind",
                      "owner_customer_id"):
            if f not in token_data or token_data[f] in (None, ""):
                return {"registered": False, "error": f"missing_field:{f}"}
        if token_data["kind"] not in PAN_FIELD_KINDS:
            return {"registered": False,
                       "error": f"invalid_kind:{token_data['kind']}"}

        # PCI DSS hardline: reject any raw PAN regardless of intent.
        for fname, fval in token_data.items():
            if _looks_like_raw_pan(fval):
                return {
                    "registered": False,
                    "error": f"raw_pan_rejected_in_field:{fname}",
                }

        # Kind-specific validation
        if token_data["kind"] == "LAST_FOUR":
            v = str(token_data["token_value"])
            if not v.isdigit() or len(v) != 4:
                return {"registered": False,
                           "error": "last_four_must_be_4_digits"}
        elif token_data["kind"] == "BIN":
            v = str(token_data["token_value"])
            if not v.isdigit() or len(v) != 6:
                return {"registered": False,
                           "error": "bin_must_be_6_digits"}
        # TOKEN — opaque string, no further check beyond raw-PAN rejection

        records = self._load(self.tokens_path,
                                "cims_pan_tokens", ("token_id",))
        if any(r.get("token_id") == token_data["token_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_token_id"}
        record = {
            "token_id": token_data["token_id"],
            "token_value": token_data["token_value"],
            "kind": token_data["kind"],
            "owner_customer_id": token_data["owner_customer_id"],
            "scheme": token_data.get("scheme", ""),
            "state": "ACTIVE",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
            "transitions": [{
                "to": "ACTIVE", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.tokens_path, records,
                          "cims_pan_tokens", "token_id")
        return {"registered": ok, "token_id": token_data["token_id"]}

    def transition_token_state(
        self, token_id: str, new_state: str,
        actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False,
                       "error": "actor_and_reason_required"}
        if new_state not in PAN_TOKEN_STATES:
            return {"transitioned": False,
                       "error": f"invalid_state:{new_state}"}
        records = self._load(self.tokens_path,
                                "cims_pan_tokens", ("token_id",))
        for r in records:
            if r.get("token_id") == token_id:
                current = r.get("state", "ACTIVE")
                allowed = ALLOWED_TOKEN_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {"transitioned": False,
                               "error": f"transition_not_allowed:{current}_to_{new_state}"}
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(self.tokens_path, records,
                                  "cims_pan_tokens", "token_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "token_not_found"}

    def register_document(
        self, doc_data: Dict[str, Any], actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"registered": False, "error": "actor_and_reason_required"}
        for f in ("document_id", "document_type",
                      "vault_reference", "owner_customer_id"):
            if f not in doc_data or not doc_data[f]:
                return {"registered": False, "error": f"missing_field:{f}"}
        if doc_data["document_type"] not in DOCUMENT_TYPES:
            return {"registered": False,
                       "error": f"invalid_document_type:{doc_data['document_type']}"}
        # Reject raw PAN sneaking in via narrative fields
        for fname, fval in doc_data.items():
            if _looks_like_raw_pan(fval):
                return {
                    "registered": False,
                    "error": f"raw_pan_rejected_in_field:{fname}",
                }
        records = self._load(self.documents_path,
                                "cims_documents", ("document_id",))
        if any(r.get("document_id") == doc_data["document_id"]
                 for r in records):
            return {"registered": False, "error": "duplicate_document_id"}
        record = {
            "document_id": doc_data["document_id"],
            "document_type": doc_data["document_type"],
            "vault_reference": doc_data["vault_reference"],
            "owner_customer_id": doc_data["owner_customer_id"],
            "linked_session_id": doc_data.get("linked_session_id", ""),
            "narrative": doc_data.get("narrative", ""),
            "state": "UPLOADED",
            "registered_by": actor,
            "registered_at": datetime.utcnow().isoformat(),
            "registration_reason": reason,
            "transitions": [{
                "to": "UPLOADED", "actor": actor,
                "at": datetime.utcnow().isoformat(),
            }],
        }
        records.append(record)
        ok = self._save(self.documents_path, records,
                          "cims_documents", "document_id")
        return {"registered": ok, "document_id": doc_data["document_id"]}

    def transition_document_state(
        self, document_id: str, new_state: str,
        actor: str, reason: str,
    ) -> Dict[str, Any]:
        if not actor or not reason:
            return {"transitioned": False,
                       "error": "actor_and_reason_required"}
        if new_state not in DOCUMENT_STATES:
            return {"transitioned": False,
                       "error": f"invalid_state:{new_state}"}
        records = self._load(self.documents_path,
                                "cims_documents", ("document_id",))
        for r in records:
            if r.get("document_id") == document_id:
                current = r.get("state", "UPLOADED")
                allowed = ALLOWED_DOCUMENT_TRANSITIONS.get(current, ())
                if new_state not in allowed:
                    return {"transitioned": False,
                               "error": f"transition_not_allowed:{current}_to_{new_state}"}
                r["state"] = new_state
                r.setdefault("transitions", []).append({
                    "to": new_state, "actor": actor,
                    "at": datetime.utcnow().isoformat(),
                    "reason": reason,
                })
                ok = self._save(self.documents_path, records,
                                  "cims_documents", "document_id")
                return {"transitioned": ok, "from": current, "to": new_state}
        return {"transitioned": False, "error": "document_not_found"}

    def record_access_event(
        self, event_data: Dict[str, Any], actor: str,
    ) -> Dict[str, Any]:
        if not actor:
            return {"recorded": False, "error": "actor_required"}
        for f in ("event_id", "event_type", "subject_id"):
            if f not in event_data or not event_data[f]:
                return {"recorded": False, "error": f"missing_field:{f}"}
        if event_data["event_type"] not in ACCESS_EVENT_TYPES:
            return {"recorded": False,
                       "error": f"invalid_event_type:{event_data['event_type']}"}
        records = self._load(self.access_events_path,
                                "cims_pan_access_events", ("event_id",))
        if any(r.get("event_id") == event_data["event_id"]
                 for r in records):
            return {"recorded": False, "error": "duplicate_event_id"}
        record = {
            "event_id": event_data["event_id"],
            "event_type": event_data["event_type"],
            "subject_id": event_data["subject_id"],
            "narrative": event_data.get("narrative", ""),
            "recorded_by": actor,
            "recorded_at": datetime.utcnow().isoformat(),
        }
        records.append(record)
        ok = self._save(self.access_events_path, records,
                          "cims_pan_access_events", "event_id")
        return {"recorded": ok, "event_id": event_data["event_id"]}

    def pan_inventory_summary(self) -> Dict[str, Any]:
        records = self._load(self.tokens_path,
                                "cims_pan_tokens", ("token_id",))
        per_state: Dict[str, int] = {}
        per_kind: Dict[str, int] = {}
        for r in records:
            s = r.get("state", "")
            per_state[s] = per_state.get(s, 0) + 1
            k = r.get("kind", "")
            per_kind[k] = per_kind.get(k, 0) + 1
        return {
            "total_tokens": len(records),
            "per_state": per_state,
            "per_kind": per_kind,
            "token_ttl_days": DEFAULT_TOKEN_TTL_DAYS,
        }

    def document_inventory_summary(self) -> Dict[str, Any]:
        records = self._load(self.documents_path,
                                "cims_documents", ("document_id",))
        per_state: Dict[str, int] = {}
        per_type: Dict[str, int] = {}
        for r in records:
            s = r.get("state", "")
            per_state[s] = per_state.get(s, 0) + 1
            t = r.get("document_type", "")
            per_type[t] = per_type.get(t, 0) + 1
        return {
            "total_documents": len(records),
            "per_state": per_state,
            "per_type": per_type,
            "retention_years": DEFAULT_DOCUMENT_RETENTION_YEARS,
        }


def _self_test() -> None:
    import tempfile

    assert PAN_TOKEN_STATES == (
        "ACTIVE", "REVOKED", "EXPIRED", "ARCHIVED",
    )
    assert ALLOWED_TOKEN_TRANSITIONS["ARCHIVED"] == ()
    assert DOCUMENT_STATES == (
        "UPLOADED", "IN_REVIEW", "VERIFIED",
        "REJECTED", "ARCHIVED",
    )
    assert ALLOWED_DOCUMENT_TRANSITIONS["VERIFIED"] == ("ARCHIVED",)
    assert ALLOWED_DOCUMENT_TRANSITIONS["REJECTED"] == ("ARCHIVED",)
    assert ALLOWED_DOCUMENT_TRANSITIONS["ARCHIVED"] == ()
    assert DOCUMENT_TYPES == (
        "NATIONAL_ID", "PASSPORT", "KRA_PIN_CERTIFICATE",
        "UTILITY_BILL", "BANK_STATEMENT",
        "BUSINESS_REGISTRATION", "PROOF_OF_INCOME", "OTHER",
    )
    assert ACCESS_EVENT_TYPES == (
        "TOKEN_LOOKUP", "DOCUMENT_VIEW", "DOCUMENT_DOWNLOAD",
        "METADATA_UPDATE", "ACCESS_DENIED",
    )
    assert PAN_FIELD_KINDS == ("TOKEN", "LAST_FOUR", "BIN")
    assert DEFAULT_TOKEN_TTL_DAYS == 365
    assert DEFAULT_DOCUMENT_RETENTION_YEARS == 7
    assert PCI_DSS_RAW_PAN_PROHIBITED is True

    # Luhn smoke
    assert _luhn_check("4111111111111111")
    assert not _luhn_check("4111111111111112")
    assert _looks_like_raw_pan("4111 1111 1111 1111")
    assert _looks_like_raw_pan("4111-1111-1111-1111")
    assert not _looks_like_raw_pan("1111")
    assert not _looks_like_raw_pan("411111")
    assert not _looks_like_raw_pan("anyhow_token_abc123")

    with tempfile.TemporaryDirectory() as tmpdir:
        e = SecurePANDocumentEngine(
            tokens_path=Path(tmpdir) / "t.json",
            documents_path=Path(tmpdir) / "d.json",
            access_events_path=Path(tmpdir) / "a.json",
        )
        # Token — opaque token
        r = e.register_token(
            {"token_id": "TKN-001",
             "token_value": "tkn_abc123xyz",
             "kind": "TOKEN",
             "owner_customer_id": "CUST-001",
             "scheme": "VISA"},
            actor="ops", reason="card linked",
        )
        assert r["registered"]
        # Token — last 4
        r = e.register_token(
            {"token_id": "TKN-002",
             "token_value": "1234",
             "kind": "LAST_FOUR",
             "owner_customer_id": "CUST-001"},
            actor="ops", reason="display",
        )
        assert r["registered"]
        # Token — BIN
        r = e.register_token(
            {"token_id": "TKN-003",
             "token_value": "411111",
             "kind": "BIN",
             "owner_customer_id": "CUST-001"},
            actor="ops", reason="routing",
        )
        assert r["registered"]
        # Reject raw PAN in token_value
        r = e.register_token(
            {"token_id": "TKN-X",
             "token_value": "4111111111111111",
             "kind": "TOKEN",
             "owner_customer_id": "CUST-X"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        assert "raw_pan_rejected" in r["error"]
        # Reject raw PAN in narrative
        r = e.register_token(
            {"token_id": "TKN-Y",
             "token_value": "tkn_xyz",
             "kind": "TOKEN",
             "owner_customer_id": "CUST-Y",
             "scheme": "4111-1111-1111-1111"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        assert "raw_pan_rejected" in r["error"]
        # Reject bad LAST_FOUR
        r = e.register_token(
            {"token_id": "TKN-Z",
             "token_value": "12",
             "kind": "LAST_FOUR",
             "owner_customer_id": "CUST-X"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Reject bad BIN
        r = e.register_token(
            {"token_id": "TKN-W",
             "token_value": "41",
             "kind": "BIN",
             "owner_customer_id": "CUST-X"},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # Token lifecycle
        r = e.transition_token_state(
            "TKN-001", "REVOKED",
            actor="ops", reason="customer requested",
        )
        assert r["transitioned"]
        # REVOKED → ARCHIVED only
        r = e.transition_token_state(
            "TKN-001", "ACTIVE", actor="x", reason="x",
        )
        assert not r["transitioned"]
        r = e.transition_token_state(
            "TKN-001", "ARCHIVED",
            actor="ops", reason="closed",
        )
        assert r["transitioned"]

        # Document
        r = e.register_document(
            {"document_id": "DOC-001",
             "document_type": "NATIONAL_ID",
             "vault_reference": "vault://cims/abc123",
             "owner_customer_id": "CUST-001"},
            actor="ops", reason="onboarding",
        )
        assert r["registered"]
        # Bad doc type
        r = e.register_document(
            {"document_id": "X",
             "document_type": "WHATEVER",
             "vault_reference": "v",
             "owner_customer_id": "Y"},
            actor="x", reason="x",
        )
        assert not r["registered"]
        # Reject raw PAN in narrative
        r = e.register_document(
            {"document_id": "DOC-X",
             "document_type": "BANK_STATEMENT",
             "vault_reference": "v",
             "owner_customer_id": "CUST-X",
             "narrative": "found 4111 1111 1111 1111 in upload"},
            actor="x", reason="x",
        )
        assert not r["registered"]

        # Document lifecycle
        r = e.transition_document_state(
            "DOC-001", "IN_REVIEW",
            actor="ops", reason="checking",
        )
        assert r["transitioned"]
        r = e.transition_document_state(
            "DOC-001", "VERIFIED",
            actor="ops", reason="passed",
        )
        assert r["transitioned"]
        # VERIFIED → ARCHIVED only
        r = e.transition_document_state(
            "DOC-001", "REJECTED", actor="x", reason="x",
        )
        assert not r["transitioned"]
        r = e.transition_document_state(
            "DOC-001", "ARCHIVED",
            actor="ops", reason="closed",
        )
        assert r["transitioned"]

        # Access event
        r = e.record_access_event(
            {"event_id": "EV-001",
             "event_type": "TOKEN_LOOKUP",
             "subject_id": "TKN-002",
             "narrative": "ops view in cockpit"},
            actor="ops",
        )
        assert r["recorded"]
        # Bad event type
        r = e.record_access_event(
            {"event_id": "X",
             "event_type": "WHATEVER",
             "subject_id": "Y"},
            actor="x",
        )
        assert not r["recorded"]

        # Inventory summaries
        s = e.pan_inventory_summary()
        assert s["total_tokens"] == 3
        assert s["per_kind"]["TOKEN"] == 1
        assert s["per_kind"]["LAST_FOUR"] == 1
        assert s["per_kind"]["BIN"] == 1
        assert s["token_ttl_days"] == 365

        d = e.document_inventory_summary()
        assert d["total_documents"] == 1
        assert d["per_type"]["NATIONAL_ID"] == 1
        assert d["retention_years"] == 7

    print("  ✅ cims_secure_pan_documents self-test PASS")


if __name__ == "__main__":
    _self_test()
