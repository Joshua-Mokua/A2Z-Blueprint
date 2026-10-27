"""Optional fail-closed Availment Memo readiness gate for CAD/TROPS manager operations.

This is an application-level precondition, NOT a cross-store atomic transaction.
"""
import json
import os
from fastapi import HTTPException


def require_availment_validation_for_release(case_id: str, require_released: bool = False) -> None:
    if os.getenv("A2Z_AVAILMENT_TROPS_GATE", "").strip() != "enabled":
        return
    from utils.db import db
    from utils.availment_dual_validation import readiness
    try:
        row = db.fetch_one(
            "SELECT id, status, current_version, data, sent_to_trops_by, sent_to_trops_at FROM credit.availment_memos WHERE credit_admin_case_id=%s",
            (case_id,),
        )
        if not row:
            raise HTTPException(status_code=409, detail="Availment Memo is required before TROPS release or disbursement")
        data = row["data"]
        if isinstance(data, str):
            data = json.loads(data)
        if not isinstance(data, dict):
            raise HTTPException(status_code=409, detail="Invalid Availment Memo data")
        if str(row["status"]).lower() != "approved":
            raise HTTPException(status_code=409, detail="Availment Memo must be approved")
        from utils.availment_memo import evaluate_readiness
        version = int(row.get("current_version") or 0)
        memo_id = str(row.get("id") or "").strip()
        if not memo_id or version < 1:
            raise HTTPException(status_code=409, detail="Approved Availment Memo version is missing")
        approved = db.fetch_one("SELECT snapshot FROM credit.availment_versions WHERE memo_id=%s AND version=%s", (memo_id, version))
        if not approved:
            raise HTTPException(status_code=409, detail="Approved Availment Memo snapshot is missing")
        snapshot = approved["snapshot"]
        if isinstance(snapshot, str):
            snapshot = json.loads(snapshot)
        if not isinstance(snapshot, dict) or not isinstance(snapshot.get("memo"), dict) or not isinstance(snapshot.get("source"), dict):
            raise HTTPException(status_code=409, detail="Invalid approved Availment Memo snapshot")
        if snapshot.get("version") != version or snapshot["memo"].get("id") != memo_id or snapshot["memo"].get("credit_admin_case_id") != case_id or snapshot["memo"].get("data") != data:
            raise HTTPException(status_code=409, detail="Approved Availment Memo version does not match current memo")
        result = evaluate_readiness(snapshot["memo"], snapshot["source"])
        if not result["ready"]:
            raise HTTPException(status_code=409, detail={"message": "Approved Availment Memo has incomplete mandatory information", "failures": result["failures"]})
        if require_released:
            if not str(row.get("sent_to_trops_by") or "").strip() or not row.get("sent_to_trops_at"):
                raise HTTPException(status_code=409, detail="Availment Memo has not been released to TROPS")
            case_row = db.fetch_one("SELECT data FROM credit_admin WHERE id=%s", (case_id,))
            if not case_row:
                raise HTTPException(status_code=409, detail="Released Credit Admin case is missing")
            case_data = case_row["data"]
            if isinstance(case_data, str):
                case_data = json.loads(case_data)
            if not isinstance(case_data, dict) or case_data.get("availment_released_version") != version or str(case_data.get("availment_released_by") or "").strip() != str(row.get("sent_to_trops_by") or "").strip() or not case_data.get("cleared_for_disbursement"):
                raise HTTPException(status_code=409, detail="TROPS release does not match the approved Availment Memo version and releasing officer")
        state = readiness(data)
        if not state["validation_complete"]:
            raise HTTPException(status_code=409, detail={
                "message": "Availment Memo validation incomplete",
                "missing_roles": state["missing_roles"],
                "blocked": state["blocked"],
            })
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail="Availment validation verification unavailable") from exc
