"""PostgreSQL-native persistence for the CAD Availment Memo."""
from __future__ import annotations
import json
from datetime import date, datetime, timezone
from decimal import Decimal
from typing import Any, Dict, Optional
from utils.db import db

EDITABLE_STATUSES = {"draft"}

CAD_EDITABLE_FIELDS = {
    "industry_code",
    "product_program_code",
    "restricted_salaried_facility_details",
    "amount_already_disbursed",
    "current_disbursement",
    "value_date",
    "review_date",
    "orr",
    "frr",
    "default_interest_rate",
    "repayment_amount",
    "repayment_frequency",
    "repayment_effective_date",
    "maturity_date",
    "drawdown_account",
    "repayment_account",
    "facility_fee",
    "fee_debit_account",
    "deferral",
    "fees_charges",
    "insurance_premium",
    "notes",
}

INSTRUCTION_TYPES = {
    "insurance_collection",
    "prior_loan_liquidation",
    "external_bank_payoff",
    "residual_lien_hold",
    "other",
}

class AvailmentPersistenceUnavailable(RuntimeError):
    pass

class AvailmentConflict(RuntimeError):
    pass

def _require_postgres() -> None:
    if not db.is_postgres_ready():
        raise AvailmentPersistenceUnavailable(
            "Availment Memo requires PostgreSQL; no JSON fallback is permitted."
        )

def _actor(user: Dict[str, Any]) -> str:
    return str(user.get("full_name") or user.get("username") or user.get("staff_code") or "").strip()

def _json_safe(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, (datetime, date, Decimal)):
        return str(value)
    return value

def _decode_json(value: Any) -> Dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    if isinstance(value, str) and value.strip():
        try:
            decoded = json.loads(value)
            return decoded if isinstance(decoded, dict) else {}
        except (TypeError, ValueError):
            return {}
    return {}

def _row_to_memo(row: Optional[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    if not row:
        return None
    result = dict(row)
    result["data"] = _decode_json(result.get("data"))
    for key in ("created_at", "updated_at", "approved_at", "sent_to_trops_at"):
        value = result.get(key)
        if isinstance(value, (datetime, date)):
            result[key] = value.isoformat()
    return result

def _fetch_one_conn(conn, sql: str, params: tuple = ()) -> Optional[Dict[str, Any]]:
    with conn.cursor() as cur:
        cur.execute(sql, params)
        row = cur.fetchone()
        if row is None:
            return None
        cols = [d[0] for d in cur.description]
        return dict(zip(cols, row))

def _memo_id(case_id: str) -> str:
    return "AVM-" + str(case_id).strip()

def get_memo(credit_admin_case_id: str) -> Optional[Dict[str, Any]]:
    _require_postgres()
    row = db.fetch_one(
        "SELECT * FROM credit.availment_memos WHERE credit_admin_case_id = %s",
        (str(credit_admin_case_id),),
    )
    return _row_to_memo(row)

def build_source_projection(case: Dict[str, Any], application: Optional[Dict[str, Any]] = None) -> Dict[str, Any]:
    app = application or {}
    return _json_safe({
        "credit_admin_case_id": case.get("id"),
        "application_id": case.get("application_id") or app.get("id"),
        "client_name": case.get("client_name") or app.get("client_name"),
        "product": case.get("product") or app.get("product"),
        "amount": case.get("amount") if case.get("amount") is not None else app.get("amount"),
        "currency": case.get("currency") or app.get("currency"),
        "approval_date": case.get("approval_date") or app.get("approved_at"),
        "conditions": case.get("conditions") or [],
        "facility_security_type": case.get("facility_security_type") or app.get("facility_security_type"),
        "security_subtype": case.get("security_subtype") or app.get("security_subtype"),
        "post_approval_verification": dict(app.get("post_approval_verification") or {}),
        "document_files": app.get("document_files") or {},
        "decision": dict(app.get("decision") or {}),
    })

def create_memo(case: Dict[str, Any], application: Optional[Dict[str, Any]], user: Dict[str, Any]) -> Dict[str, Any]:
    _require_postgres()
    case_id = str(case.get("id") or "").strip()
    application_id = str(case.get("application_id") or "").strip()
    actor = _actor(user)
    creator_code = _identity_code(user)
    if not case_id or not application_id:
        raise ValueError("CAD case id and application id are required")
    if not actor or not creator_code:
        raise ValueError("Authenticated actor with canonical identity is required")
    memo_id = _memo_id(case_id)
    initial_data = {"fields": {}, "instructions": []}
    with db.transaction() as conn:
        existing = _fetch_one_conn(
            conn,
            "SELECT * FROM credit.availment_memos WHERE credit_admin_case_id = %s FOR UPDATE",
            (case_id,),
        )
        if existing:
            return _row_to_memo(existing) or {}
        db.execute(
            "INSERT INTO credit.availment_memos "
            "(id, credit_admin_case_id, application_id, status, current_version, data, created_by, created_by_code, updated_by) "
            "VALUES (%s, %s, %s, 'draft', 0, %s::jsonb, %s, %s, %s) "
            "ON CONFLICT (credit_admin_case_id) DO NOTHING",
            (memo_id, case_id, application_id, json.dumps(initial_data), actor, creator_code, actor),
            conn=conn,
        )
        created = _fetch_one_conn(
            conn,
            "SELECT * FROM credit.availment_memos WHERE credit_admin_case_id = %s",
            (case_id,),
        )
    if not created:
        raise AvailmentConflict("Availment Memo could not be created")
    return _row_to_memo(created) or {}

def save_draft(credit_admin_case_id: str, fields: Dict[str, Any], instructions: list, user: Dict[str, Any]) -> Dict[str, Any]:
    _require_postgres()
    case_id = str(credit_admin_case_id or "").strip()
    actor = _actor(user)
    if not case_id or not actor:
        raise ValueError("CAD case id and authenticated actor are required")
    with db.transaction() as conn:
        row = _fetch_one_conn(
            conn,
            "SELECT * FROM credit.availment_memos WHERE credit_admin_case_id = %s FOR UPDATE",
            (case_id,),
        )
        if not row:
            raise KeyError("Availment Memo has not been started")
        if str(row.get("status") or "") not in EDITABLE_STATUSES:
            raise AvailmentConflict("Approved or transmitted Availment Memo versions are immutable.")
        submitted_fields = dict(fields or {})
        prohibited = sorted(set(submitted_fields) - CAD_EDITABLE_FIELDS)
        if prohibited:
            raise ValueError(
                "Non-editable Availment fields: " + ", ".join(prohibited)
            )

        submitted_instructions = list(instructions or [])
        for instruction in submitted_instructions:
            if not isinstance(instruction, dict):
                raise ValueError("Each Availment instruction must be an object")
            instruction_type = str(instruction.get("type") or "").strip()
            if instruction_type not in INSTRUCTION_TYPES:
                raise ValueError(
                    "Unsupported Availment instruction type: " + instruction_type
                )

        data = _decode_json(row.get("data"))
        data["fields"] = _json_safe(submitted_fields)
        data["instructions"] = _json_safe(submitted_instructions)
        db.execute(
            "UPDATE credit.availment_memos SET data = %s::jsonb, updated_by = %s, updated_at = now() "
            "WHERE credit_admin_case_id = %s",
            (json.dumps(data), actor, case_id),
            conn=conn,
        )
        saved = _fetch_one_conn(
            conn,
            "SELECT * FROM credit.availment_memos WHERE credit_admin_case_id = %s",
            (case_id,),
        )
    return _row_to_memo(saved) or {}

def _identity_code(user: Dict[str, Any]) -> str:
    return str(user.get("staff_code") or user.get("username") or "").strip().casefold()


def _approval_identity_guard(row: Dict[str, Any], approver_code: str, *, check_requester: bool) -> None:
    """Fail closed on missing original-maker provenance or SoD conflicts."""
    creator_code = str(row.get("created_by_code") or "").strip().casefold()
    if not creator_code:
        raise AvailmentConflict("Original memo maker identity is unverified; approval is blocked")
    if approver_code == creator_code:
        raise AvailmentConflict("Maker/checker separation: original memo maker cannot approve")
    if check_requester:
        requester_code = str(row.get("approval_requested_by_code") or "").strip().casefold()
        if not requester_code:
            raise AvailmentConflict("Approval requester identity is unverified; approval is blocked")
        if approver_code == requester_code:
            raise AvailmentConflict("Maker/checker separation: approval requester cannot approve")


def evaluate_readiness(
    memo: Dict[str, Any],
    source: Dict[str, Any],
) -> Dict[str, Any]:
    data = _decode_json(memo.get("data"))
    fields = dict(data.get("fields") or {})
    instructions = list(data.get("instructions") or [])
    failures = []
    if not str(source.get("application_id") or "").strip():
        failures.append("Linked loan application is required")
    if not str(source.get("client_name") or "").strip():
        failures.append("Client name is required")
    if source.get("amount") in (None, ""):
        failures.append("Approved facility amount is required")
    if not str(source.get("currency") or "").strip():
        failures.append("Facility currency is required")
    # C2 enforces only universal operational requirements here.
    # Product-specific/applicability requirements must come from an
    # authoritative product/configuration rule, not from the sample memo.
    required_fields = {
        "current_disbursement": "Current disbursement amount",
        "value_date": "Value/effective date",
    }
    for key, label in required_fields.items():
        value = fields.get(key)
        if value is None or (isinstance(value, str) and not value.strip()):
            failures.append(f"{label} is required")
    for index, instruction in enumerate(instructions, start=1):
        if not isinstance(instruction, dict):
            failures.append(f"Instruction {index} must be an object")
            continue
        instruction_type = str(instruction.get("type") or "").strip()
        if instruction_type not in INSTRUCTION_TYPES:
            failures.append(f"Instruction {index} has unsupported type")
    return {"ready": not failures, "failures": failures}


def request_approval(
    credit_admin_case_id: str,
    source: Dict[str, Any],
    user: Dict[str, Any],
    assignee: Dict[str, Any],
    note: str = "",
) -> Dict[str, Any]:
    _require_postgres()
    case_id = str(credit_admin_case_id or "").strip()
    actor = _actor(user)
    actor_code = _identity_code(user)
    assignee_code = str(assignee.get("staff_code") or assignee.get("username") or "").strip()
    assignee_identity = _identity_code(assignee)
    if not case_id or not actor or not actor_code:
        raise ValueError("CAD case id and authenticated actor are required")
    if not assignee_code or not assignee_identity:
        raise ValueError("Availment approval assignee is required")
    if assignee_identity == actor_code:
        raise AvailmentConflict("Maker/checker separation: you cannot approve your own Availment Memo")
    with db.transaction() as conn:
        row = _fetch_one_conn(conn, "SELECT * FROM credit.availment_memos WHERE credit_admin_case_id = %s FOR UPDATE", (case_id,))
        if not row:
            raise KeyError("Availment Memo has not been started")
        if str(row.get("status") or "") != "draft":
            raise AvailmentConflict("Only a draft Availment Memo may be submitted for approval")
        _approval_identity_guard(row, assignee_identity, check_requester=False)
        readiness = evaluate_readiness(_row_to_memo(row) or {}, source)
        if not readiness["ready"]:
            raise AvailmentConflict("Availment Memo is not ready for approval: " + "; ".join(readiness["failures"]))
        db.execute("UPDATE credit.availment_memos SET status = 'ready_for_approval', approval_assignee_code = %s, approval_assignee_name = %s, approval_assignee_role = %s, approval_requested_by = %s, approval_requested_by_code = %s, approval_requested_at = now(), approval_note = %s, updated_by = %s, updated_at = now() WHERE credit_admin_case_id = %s", (assignee_code, str(assignee.get("full_name") or assignee_code), str(assignee.get("role") or ""), actor, str(user.get("staff_code") or user.get("username") or "").strip(), str(note or ""), actor, case_id), conn=conn)
        saved = _fetch_one_conn(conn, "SELECT * FROM credit.availment_memos WHERE credit_admin_case_id = %s", (case_id,))
    return _row_to_memo(saved) or {}



def return_for_correction(
    credit_admin_case_id: str,
    user: Dict[str, Any],
    reason: str,
) -> Dict[str, Any]:
    _require_postgres()
    case_id = str(credit_admin_case_id or "").strip()
    actor = _actor(user)
    actor_code = _identity_code(user)
    return_reason = str(reason or "").strip()
    if not case_id or not actor or not actor_code:
        raise ValueError("CAD case id and authenticated actor are required")
    if not return_reason:
        raise ValueError("Return reason is required")
    with db.transaction() as conn:
        row = _fetch_one_conn(conn, "SELECT * FROM credit.availment_memos WHERE credit_admin_case_id = %s FOR UPDATE", (case_id,))
        if not row:
            raise KeyError("Availment Memo has not been started")
        if str(row.get("status") or "") != "ready_for_approval":
            raise AvailmentConflict("Only an Availment Memo awaiting approval may be returned for correction")
        selected = str(row.get("approval_assignee_code") or "").strip().casefold()
        if not selected or selected != actor_code:
            raise AvailmentConflict("Only the selected Availment approver may return this memo for correction")
        data = _decode_json(row.get("data"))
        history = list(data.get("approval_returns") or [])
        history.append(_json_safe({"reason": return_reason, "returned_by": actor, "returned_by_code": str(user.get("staff_code") or user.get("username") or "").strip(), "returned_at": datetime.now(timezone.utc).isoformat()}))
        data["approval_returns"] = history
        db.execute("UPDATE credit.availment_memos SET status = 'draft', data = %s::jsonb, approval_assignee_code = NULL, approval_assignee_name = NULL, approval_assignee_role = NULL, updated_by = %s, updated_at = now() WHERE credit_admin_case_id = %s", (json.dumps(_json_safe(data)), actor, case_id), conn=conn)
        saved = _fetch_one_conn(conn, "SELECT * FROM credit.availment_memos WHERE credit_admin_case_id = %s", (case_id,))
    return _row_to_memo(saved) or {}

def approve_memo(
    credit_admin_case_id: str,
    source: Dict[str, Any],
    user: Dict[str, Any],
) -> Dict[str, Any]:
    _require_postgres()
    case_id = str(credit_admin_case_id or "").strip()
    actor = _actor(user)
    actor_code = _identity_code(user)
    if not case_id or not actor or not actor_code:
        raise ValueError("CAD case id and authenticated actor are required")
    with db.transaction() as conn:
        row = _fetch_one_conn(conn, "SELECT * FROM credit.availment_memos WHERE credit_admin_case_id = %s FOR UPDATE", (case_id,))
        if not row:
            raise KeyError("Availment Memo has not been started")
        if str(row.get("status") or "") != "ready_for_approval":
            raise AvailmentConflict("Availment Memo is not awaiting approval")
        selected = str(row.get("approval_assignee_code") or "").strip()
        selected_identity = selected.casefold()
        if not selected_identity or selected_identity != actor_code:
            raise AvailmentConflict("Only the selected Availment approver may approve this memo")
        _approval_identity_guard(row, actor_code, check_requester=True)
        memo = _row_to_memo(row) or {}
        readiness = evaluate_readiness(memo, source)
        if not readiness["ready"]:
            raise AvailmentConflict("Availment Memo is no longer ready for approval: " + "; ".join(readiness["failures"]))
        version = int(row.get("current_version") or 0) + 1
        snapshot = _json_safe({"memo": {"id": memo.get("id"), "credit_admin_case_id": memo.get("credit_admin_case_id"), "application_id": memo.get("application_id"), "created_by_code": row.get("created_by_code"), "data": memo.get("data") or {}}, "source": source, "approval": {"requested_by": row.get("approval_requested_by"), "requested_by_code": row.get("approval_requested_by_code"), "requested_at": row.get("approval_requested_at"), "request_note": row.get("approval_note"), "assignee_code": row.get("approval_assignee_code"), "assignee_name": row.get("approval_assignee_name"), "assignee_role": row.get("approval_assignee_role"), "approved_by": actor, "approved_by_code": str(user.get("staff_code") or user.get("username") or "").strip()}, "version": version})
        db.execute("INSERT INTO credit.availment_versions (memo_id, version, snapshot, created_by) VALUES (%s, %s, %s::jsonb, %s)", (str(row.get("id") or ""), version, json.dumps(snapshot), actor), conn=conn)
        db.execute("UPDATE credit.availment_memos SET status = 'approved', current_version = %s, approved_by = %s, approved_at = now(), updated_by = %s, updated_at = now() WHERE credit_admin_case_id = %s", (version, actor, actor, case_id), conn=conn)
        saved = _fetch_one_conn(conn, "SELECT * FROM credit.availment_memos WHERE credit_admin_case_id = %s", (case_id,))
    return _row_to_memo(saved) or {}
