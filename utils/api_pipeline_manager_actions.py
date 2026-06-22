"""utils/api_pipeline_manager_actions.py — Helpers for manager-only
pipeline actions (validate, cancel approval, queue access).

Authored v10.508 Phase 3 Arc α Batch α6 — Manager Queues.

Purpose
-------
Encapsulates the role-detection logic that determines whether a user
has manager authority over pipeline deals in their cascade scope.
Also defines minimum payload validation for the new cancel-request
endpoint (RM-side action).

Doctrine context
----------------
The Streamlit pipeline page treats "manager" as a substring-match
on the user's role string (``pages/3_pipeline.py:39``). α6 mirrors
that exactly — the same keywords, the same OR-with-is_admin rule.
This keeps Streamlit and API decisions equivalent.

Cascade scope for managers is *already* handled by α2's
``get_visible_staff_codes`` — managers see deals from staff under
their cascade. The α6 endpoints reuse that machinery rather than
inventing a parallel scoping rule.

Authority model
---------------
For each α6 endpoint:

- **GET /api/pipeline/queues/validation** — manager-only (403 otherwise)
- **GET /api/pipeline/queues/cancellation** — manager-only (403 otherwise)
- **POST /api/pipeline/deals/{id}/validate** — manager-only + scope
- **POST /api/pipeline/deals/{id}/cancel/request** — any authenticated
  user, but the target deal must be in the caller's cascade scope
- **POST /api/pipeline/deals/{id}/cancel/approve** — manager-only + scope

The deliberate asymmetry: any RM can REQUEST cancellation (for deals
they own or backup), but only managers can APPROVE. This mirrors
Streamlit's flow exactly.
"""
from __future__ import annotations

from typing import Any, Dict, Tuple


# ────────────────────────────────────────────────────────────────────
# Manager role detection (Streamlit parity)
# ────────────────────────────────────────────────────────────────────


# Substrings that identify a manager role. Match must be case-insensitive
# substring match — exactly as Streamlit page line 39 implements. Any
# role string that contains any of these substrings → manager.
#
# This list is the load-bearing source of truth for α6 authorization.
# If you add a new manager role to the org tree (e.g. "team lead"),
# add the corresponding keyword here AND to pages/3_pipeline.py:39.
# Drift between the two will cause Streamlit and API to disagree on
# who's a manager — a class of UX bug that's hard to debug.
MANAGER_ROLE_KEYWORDS: Tuple[str, ...] = (
    "managing",         # MD
    "director",         # Director CCB / Director CIB
    "head of",          # Head of Retail / Head of SME / Head of Corporate
    "regional",         # Regional Head
    "branch manager",   # Branch Manager
    "chief",            # Chief Risk Officer, etc.
    "manager",          # Generic — Branch Credit Manager / Operations Mgr
    "supervisor",       # Operations supervisors
    "credit manager",   # Explicit (redundant with "manager" but explicit)
    "operations manager",  # Explicit (redundant with "manager" but explicit)
)


def is_manager(user: Dict[str, Any]) -> bool:
    """Return True if the user has manager authority over their cascade.

    Mirrors ``pages/3_pipeline.py:39`` exactly:
    ``is_admin or any(k in role.lower() for k in MANAGER_ROLE_KEYWORDS)``

    Notes:
    - `is_admin=True` automatically counts as manager (admins can do
      anything in their scope, which is the whole bank).
    - Empty/missing role string returns False (with non-admin).
    - Match is case-insensitive substring.
    """
    if not user:
        return False
    if user.get("is_admin"):
        return True
    role = str(user.get("role", "") or "").lower().strip()
    if not role:
        return False
    return any(kw in role for kw in MANAGER_ROLE_KEYWORDS)


# ────────────────────────────────────────────────────────────────────
# Cancel request validation (RM-side action)
# ────────────────────────────────────────────────────────────────────


# Minimum chars for a cancellation reason. Lower than the manager
# override note (10 chars) because cancel reasons can be legitimately
# terse — "dup", "lost to NCBA", "wrong segment", "abandoned by client".
# 5 chars rules out empty / "ok" / "no" / "x" but allows real cases.
MIN_CANCEL_REASON_LEN: int = 5


def validate_cancel_request_payload(deal_data: Dict[str, Any]) -> Tuple[bool, str]:
    """Return (ok, reason) for a cancellation-request payload.

    The PipelineManager.request_cancel method writes the reason into
    ``cancel_reason`` field on the deal. Managers see this reason in
    their cancellation queue when deciding whether to approve. An
    empty or one-word reason gives the manager nothing to evaluate.
    """
    reason = str(deal_data.get("reason", "") or "").strip()
    if not reason:
        return False, "Missing required field: reason"
    if len(reason) < MIN_CANCEL_REASON_LEN:
        return False, (
            f"reason too short ({len(reason)} chars); minimum "
            f"{MIN_CANCEL_REASON_LEN} characters required to give the "
            "manager context for their decision."
        )
    return True, ""
