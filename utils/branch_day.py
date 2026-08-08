"""
A2Z Daily Log — branch-day submission (additive, new module).

TWO-TIER VALIDATION (ruling 2026-08-08):

    tier 1  Branch Manager / triad   validates each staff log, then SUBMITS the
                                     branch day, carrying the branch index
    tier 2  Head of Branches         validates the BRANCH SUBMISSION, or returns
                                     it to the BM. Never touches individual logs;
                                     may inspect them read-only.

This module owns the object tier 2 acts on. One record per branch per day:

    draft -> submitted -> validated
                    \\-> returned -> submitted (resubmit)

WHAT IT DELIBERATELY DOES NOT DO
  * decide who may act — that is org_validator.branches_validated_by and
    staff_validated_by. This module records; it does not authorise.
  * recompute the branch index — the caller passes the figure the queue
    endpoint computed, so one formula lives in one place.
  * gate on over-reporting — reconcile_branch_day does that, and the API layer
    applies it as a precondition. Storing a submission that the gate should have
    blocked is a caller bug, not a storage concern.

Store: data/branch_days.json, written atomically (mkstemp/fsync/os.replace) so a
crash mid-write cannot leave a truncated file — the failure mode that cost this
codebase a pipeline config.
"""
from __future__ import annotations

import json
import os
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Optional

from utils.core import DATA_DIR

_STORE = Path(DATA_DIR) / "branch_days.json"

STATUS_DRAFT = "draft"
STATUS_SUBMITTED = "submitted"
STATUS_VALIDATED = "validated"
STATUS_RETURNED = "returned"


def _key(branch: str, day: str) -> str:
    return f"{str(branch).strip()}|{str(day)[:10]}"


def _load() -> dict:
    try:
        raw = json.loads(_STORE.read_text(encoding="utf-8"))
        return raw if isinstance(raw, dict) else {}
    except FileNotFoundError:
        return {}
    except Exception:
        # A corrupt store must not silently become an empty one: callers would
        # then re-submit days that were already validated. Surface it.
        raise


def _save(data: dict) -> None:
    _STORE.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp = tempfile.mkstemp(dir=str(_STORE.parent), suffix=".tmp")
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as fh:
            json.dump(data, fh, indent=2, ensure_ascii=False)
            fh.flush()
            os.fsync(fh.fileno())
        os.replace(tmp, _STORE)
    except Exception:
        try:
            os.unlink(tmp)
        except OSError:
            pass
        raise


def get_branch_day(branch: str, day: str) -> Optional[dict]:
    """The submission record for one branch-day, or None."""
    return _load().get(_key(branch, day))


def list_branch_days(day: str, branches=None) -> dict:
    """{branch: record} for a date, optionally restricted to a branch list."""
    data = _load()
    want = {str(b).strip() for b in branches} if branches else None
    out = {}
    for k, rec in data.items():
        b, _, d = k.partition("|")
        if d != str(day)[:10]:
            continue
        if want is not None and b not in want:
            continue
        out[b] = rec
    return out


def submit_branch_day(branch: str, day: str, by_code: str, by_name: str,
                      branch_index: float, staff_totals: dict,
                      control_totals: dict, counts: dict) -> dict:
    """TIER 1: the Branch Manager closes the day.

    Re-submitting after a return is allowed and clears the returned state, so a
    corrected day can flow again without an admin unlock.
    """
    data = _load()
    k = _key(branch, day)
    prev = data.get(k) or {}
    now = datetime.now().isoformat()
    rec = {
        "branch": str(branch).strip(),
        "date": str(day)[:10],
        "status": STATUS_SUBMITTED,
        "branch_index": round(float(branch_index or 0), 2),
        "staff_totals": dict(staff_totals or {}),
        "control_totals": dict(control_totals or {}),
        "counts": dict(counts or {}),          # filed / validated / expected
        "submitted_by": str(by_code or ""),
        "submitted_by_name": str(by_name or ""),
        "submitted_at": now,
        # cleared on resubmit — a returned day that comes back is pending again
        "returned_by": "", "returned_by_name": "", "returned_at": "",
        "return_note": "",
        "validated_by": prev.get("validated_by", ""),
        "validated_by_name": prev.get("validated_by_name", ""),
        "validated_at": prev.get("validated_at", ""),
        "resubmit_count": int(prev.get("resubmit_count", 0)) + (1 if prev else 0),
        "history": list(prev.get("history", [])) + [
            {"at": now, "action": "submitted", "by": str(by_code or "")}],
    }
    if prev.get("status") == STATUS_VALIDATED:
        # A validated day being resubmitted must lose its validation: the
        # numbers changed, so the countersignature no longer refers to them.
        rec["validated_by"] = rec["validated_by_name"] = rec["validated_at"] = ""
    data[k] = rec
    _save(data)
    return rec


def validate_branch_day(branch: str, day: str, by_code: str, by_name: str,
                        note: str = "") -> dict:
    """TIER 2: the Head of Branches countersigns the branch day."""
    data = _load()
    k = _key(branch, day)
    rec = data.get(k)
    if not rec:
        raise ValueError(f"{branch} has not submitted {day}")
    if rec.get("status") != STATUS_SUBMITTED:
        raise ValueError(
            f"{branch} {day} is '{rec.get('status')}' — only a submitted day can be validated")
    now = datetime.now().isoformat()
    rec.update({
        "status": STATUS_VALIDATED,
        "validated_by": str(by_code or ""),
        "validated_by_name": str(by_name or ""),
        "validated_at": now,
        "validation_note": str(note or ""),
    })
    rec.setdefault("history", []).append(
        {"at": now, "action": "validated", "by": str(by_code or "")})
    data[k] = rec
    _save(data)
    return rec


def return_branch_day(branch: str, day: str, by_code: str, by_name: str,
                      note: str) -> dict:
    """TIER 2: send the branch day back to the Branch Manager.

    A note is REQUIRED — a returned day with no reason leaves the BM nothing to
    act on, the same rule the individual return already enforces.
    """
    if not str(note or "").strip():
        raise ValueError("a note is required when returning a branch day")
    data = _load()
    k = _key(branch, day)
    rec = data.get(k)
    if not rec:
        raise ValueError(f"{branch} has not submitted {day}")
    if rec.get("status") not in (STATUS_SUBMITTED, STATUS_VALIDATED):
        raise ValueError(
            f"{branch} {day} is '{rec.get('status')}' — nothing to return")
    now = datetime.now().isoformat()
    rec.update({
        "status": STATUS_RETURNED,
        "returned_by": str(by_code or ""),
        "returned_by_name": str(by_name or ""),
        "returned_at": now,
        "return_note": str(note).strip(),
    })
    rec.setdefault("history", []).append(
        {"at": now, "action": "returned", "by": str(by_code or "")})
    data[k] = rec
    _save(data)
    return rec
