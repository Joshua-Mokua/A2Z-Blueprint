"""utils/api_roles.py — Roles API for React SPA.

v10.499 Stage C Batch 2c — Exposes the canonical role registry as a
single JSON endpoint for the React frontend.

The React SPA fetches GET /api/roles/registry once after authentication
(in the useRole() hook at app boot), populates a RoleRegistry context,
and uses it to answer schema-level questions client-side without
re-hitting the API:

  - "What are all the SBUs?" (filter dropdowns)
  - "What is the tier of role X?" (capability checks)
  - "Is role string Y canonical?" (validation)
  - "What roles belong to Retail Banking SBU?" (admin UI)

Paired with /api/auth/whoami-detailed (Batch 2b), which returns the
caller's identity. The hook calls both endpoints at boot:
  - whoami-detailed → "who am I?" → user identity cache
  - /api/roles/registry → "what is the role registry?" → schema cache

This endpoint is AUTHENTICATED (Depends(get_current_user)) but not
role-restricted. The role registry is system schema, not a secret, but
we don't expose it to anonymous callers — that's more conservative
than /api/branding (public for login page) and less restrictive than
role-gated endpoints like /api/dashboard/md.

PATTERN: Mirrors utils/api_branding.py, utils/api_cascade.py.
Mounted in utils/api.py via app.include_router(roles_router).
"""
from __future__ import annotations

from dataclasses import asdict
from typing import Any, Dict, List

from fastapi import APIRouter, Depends

from utils.auth_jwt import get_current_user
from utils.role_taxonomy import (
    ALL_SBUS,
    ALL_SCOPES,
    ALL_TIERS,
    classify_role,
    list_all_classified_roles,
)


router = APIRouter(prefix="/api/roles", tags=["roles"])


@router.get("/registry")
def get_role_registry(user: dict = Depends(get_current_user)) -> Dict[str, Any]:
    """Return the canonical role registry for React useRole() consumption.

    Auth: any authenticated user. No role restriction — the registry is
    schema, not per-user data.

    Response shape (stable contract for React SPA):
      {
        "enums": {
          "tiers":  [str, ...]   the 5 profitability tiers
          "sbus":   [str, ...]   the 7 SBUs
          "scopes": [str, ...]   the 3 branch scopes
        },
        "roles": [
          {
            "role":          str  canonical role name
            "tier":          str  one of enums.tiers
            "branch_scope":  str  one of enums.scopes
            "sbu":           str  one of enums.sbus
            "matched_via":   str  always "explicit" in this endpoint
            "can_be_tagged": bool true iff tier in {portfolio_owner, service}
          }, ...
        ],
        "total_classified_roles": int  count of explicit classifications
      }

    The "roles" array contains only EXPLICITLY classified roles (those
    present in data/org_hierarchy_config.json::profitability_axis.role_classification).
    Roles that classify via keyword fallback are NOT included — the
    registry is the canonical schema, and keyword-matched roles are a
    safety net, not a canonical declaration. If a role isn't in the
    registry, the React side should treat it as needing explicit
    classification before it can be relied upon for UI decisions.

    The "can_be_tagged" derivation matches /api/auth/whoami-detailed:
    portfolio_owner + service tiers only. Mirrors the rule in
    role_taxonomy.can_be_tagged() and the constitutional invariant
    that only these tiers may appear in accounts.csv::relationship_manager_code.

    Used by: frontend/web/src/hooks/useRole.ts (Batch 2d).
    """
    # Pull every explicitly classified role and pair it with its
    # classification. classify_role() returns a RoleClassification
    # dataclass; dataclasses.asdict() converts it to a plain dict for
    # FastAPI's JSON serialiser, which doesn't natively serialise
    # dataclasses.
    classified_roles: List[Dict[str, Any]] = []
    for role_name in list_all_classified_roles():
        classification = classify_role(role_name)
        role_dict = asdict(classification)
        # Add the derived can_be_tagged flag inline (same derivation as
        # /api/auth/whoami-detailed for consistency at the route boundary).
        role_dict["can_be_tagged"] = classification.tier in {"portfolio_owner", "service"}
        classified_roles.append(role_dict)

    response = {
        "enums": {
            "tiers":  list(ALL_TIERS),
            "sbus":   list(ALL_SBUS),
            "scopes": list(ALL_SCOPES),
        },
        "roles": classified_roles,
        "total_classified_roles": len(classified_roles),
    }

    # NB: no _audit() call here. The registry endpoint is read-only schema
    # and may be called frequently by clients on hook initialisation;
    # auditing every read would flood data/audit_log.json with noise.
    # Same rationale as /api/auth/me (also unaudited). Compare to
    # /api/auth/whoami-detailed which IS audited because it returns
    # substantive per-user identity data.

    return response