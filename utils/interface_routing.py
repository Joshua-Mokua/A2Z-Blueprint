"""utils.interface_routing — Three-Interface Strategy
(Standard #36, v5.51). Volume Five — Frontend Architecture.

Per the master spec (table form):

    | User      | Primary           | Secondary  |
    |-----------|-------------------|------------|
    | Executive | React SPA + Mobile| Streamlit  |
    | Manager   | React SPA         | Streamlit  |
    | Staff     | React SPA         | Mobile     |
    | Admin     | Streamlit         | None       |

WHAT THIS MODULE SHIPS
----------------------
A pure Python routing/policy module that:

  1. Encodes the spec table byte-for-byte as INTERFACE_ROUTING
  2. Provides accessors get_primary_interface(role), get_secondary_interface(role)
  3. Provides interface_for_user(user_dict) that combines role + device hints
  4. Exposes constants for interface names so other modules don't hard-code strings

WHY ROUTING POLICY MATTERS
---------------------------
The spec table is a real product decision: it says executives get a
mobile-friendly experience; admins are explicitly Streamlit-only because
admin pages are too dense for a mobile/React rewrite to be worth the
effort. The routing decision drives:

  - Which UI build the login flow redirects to (post-auth)
  - Which API endpoints the SPA needs (everything Manager + Executive use)
  - Which features ship on mobile (executive-relevant subset only)
  - Which pages stay Streamlit-only (#39 enforces this for Admin)

A naive "everyone gets the same UI" approach would either bloat the
React SPA with admin features (slow first-load, security surface) OR
force admins onto a mobile-friendly UI that breaks their workflow.

HONESTY DISCIPLINE
------------------
Two things this module guarantees:

  1. The routing table matches the spec **byte-for-byte**. Audit gate
     G43 enforces this with an inline check.
  2. interface_for_user() returns None on unknown role — NOT a guessed
     default. Silent fallback to the wrong UI would be a privilege
     escalation risk (e.g. an unrecognised role getting Admin access).

WHAT THIS MODULE DOES NOT DO
----------------------------
- Render any UI. This is a pure policy/routing layer.
- Assert which UI a user IS using. It only says which they SHOULD use.
- Authenticate users. The role comes from the existing auth layer
  (FastAPI Depends(get_current_user)).
"""
from __future__ import annotations

from typing import Any, Dict, List, Optional


# ─────────────────────────────────────────────────────────────────────
# Spec literals — interface names
# ─────────────────────────────────────────────────────────────────────

INTERFACE_REACT_SPA  = "React SPA"
INTERFACE_MOBILE     = "Mobile"
INTERFACE_STREAMLIT  = "Streamlit"

# The spec quotes "React SPA + Mobile" for the Executive primary slot.
# Treated as a single composite primary (executives can use EITHER).
INTERFACE_REACT_SPA_PLUS_MOBILE = "React SPA + Mobile"

# Spec literal — used for Admin secondary
INTERFACE_NONE = "None"


# ─────────────────────────────────────────────────────────────────────
# The spec table — preserved BYTE-FOR-BYTE
# ─────────────────────────────────────────────────────────────────────

INTERFACE_ROUTING: Dict[str, Dict[str, str]] = {
    "Executive": {
        "primary":   "React SPA + Mobile",
        "secondary": "Streamlit",
    },
    "Manager": {
        "primary":   "React SPA",
        "secondary": "Streamlit",
    },
    "Staff": {
        "primary":   "React SPA",
        "secondary": "Mobile",
    },
    "Admin": {
        "primary":   "Streamlit",
        "secondary": "None",
    },
}

# Roles the spec defines explicitly. Used by validators and route
# generators. Order matches the spec table top-to-bottom.
SPEC_ROLES: List[str] = ["Executive", "Manager", "Staff", "Admin"]


# ─────────────────────────────────────────────────────────────────────
# Accessors
# ─────────────────────────────────────────────────────────────────────

def get_primary_interface(role: str) -> Optional[str]:
    """Return the primary interface name for a role.

    Returns None on unknown role (NOT a guessed default — silent
    fallback to wrong UI is a privilege escalation risk).
    """
    if not role or not isinstance(role, str):
        return None
    entry = INTERFACE_ROUTING.get(role)
    return entry.get("primary") if entry else None


def get_secondary_interface(role: str) -> Optional[str]:
    """Return the secondary interface name for a role.

    Returns None for Admin (per spec) AND for unknown roles. Callers
    that need to distinguish "Admin (secondary=None per spec)" from
    "unknown role" should check role membership in SPEC_ROLES first.
    """
    if not role or not isinstance(role, str):
        return None
    entry = INTERFACE_ROUTING.get(role)
    if not entry:
        return None
    secondary = entry.get("secondary")
    # Spec literal "None" → Python None
    return None if secondary == "None" else secondary


def interface_for_user(
    user: Optional[Dict[str, Any]],
    *,
    device_hint: Optional[str] = None,
) -> Optional[str]:
    """Return the actual interface name for a user.

    user: dict with at least a "role" key (matching SPEC_ROLES).
    device_hint: "mobile", "desktop", or None. When the user's primary
        interface is "React SPA + Mobile", a "mobile" device_hint
        resolves to "Mobile"; "desktop" resolves to "React SPA"; None
        defaults to "React SPA" (web is the larger surface).

    Returns None for missing/invalid user (NOT a default).
    """
    if not user or not isinstance(user, dict):
        return None
    role = user.get("role")
    primary = get_primary_interface(role)
    if not primary:
        return None
    if primary == INTERFACE_REACT_SPA_PLUS_MOBILE:
        if device_hint == "mobile":
            return INTERFACE_MOBILE
        # desktop or unspecified → SPA
        return INTERFACE_REACT_SPA
    return primary


def all_interfaces_for_role(role: str) -> List[str]:
    """Return [primary, secondary] flattened for a role.

    For Executive primary "React SPA + Mobile" expands to ["React SPA",
    "Mobile"]. Admin returns ["Streamlit"] only (secondary is None).
    """
    if role not in INTERFACE_ROUTING:
        return []
    out: List[str] = []
    primary = INTERFACE_ROUTING[role]["primary"]
    if primary == INTERFACE_REACT_SPA_PLUS_MOBILE:
        out.extend([INTERFACE_REACT_SPA, INTERFACE_MOBILE])
    else:
        out.append(primary)
    secondary = INTERFACE_ROUTING[role]["secondary"]
    if secondary and secondary != "None":
        out.append(secondary)
    return out


# ─────────────────────────────────────────────────────────────────────
# Validator — used by audit gate G43
# ─────────────────────────────────────────────────────────────────────

def validate_interface_routing() -> Dict[str, Any]:
    """End-to-end validation of the routing table against spec.

    Returns: {"valid": bool, "errors": list[str], "roles_validated": int}
    """
    errors: List[str] = []

    # Spec table byte-for-byte
    expected = {
        "Executive": {"primary": "React SPA + Mobile", "secondary": "Streamlit"},
        "Manager":   {"primary": "React SPA",          "secondary": "Streamlit"},
        "Staff":     {"primary": "React SPA",          "secondary": "Mobile"},
        "Admin":     {"primary": "Streamlit",          "secondary": "None"},
    }

    for role, exp in expected.items():
        actual = INTERFACE_ROUTING.get(role)
        if not actual:
            errors.append(f"role {role!r} missing from INTERFACE_ROUTING")
            continue
        if actual.get("primary") != exp["primary"]:
            errors.append(
                f"role {role!r} primary={actual.get('primary')!r} "
                f"!= spec {exp['primary']!r}"
            )
        if actual.get("secondary") != exp["secondary"]:
            errors.append(
                f"role {role!r} secondary={actual.get('secondary')!r} "
                f"!= spec {exp['secondary']!r}"
            )

    # No extra roles silently added (spec is the contract)
    extra = set(INTERFACE_ROUTING.keys()) - set(expected.keys())
    if extra:
        errors.append(f"extra roles not in spec: {sorted(extra)}")

    return {
        "valid":           len(errors) == 0,
        "errors":          errors,
        "roles_validated": len(INTERFACE_ROUTING),
    }


# ─────────────────────────────────────────────────────────────────────
# Self-test
# ─────────────────────────────────────────────────────────────────────

if __name__ == "__main__":
    print("A2Z MIS 360 — utils.interface_routing self-test")

    # ── Spec table byte-for-byte ─────────────────────────────────────
    v = validate_interface_routing()
    assert v["valid"], f"spec mismatch: {v['errors']}"
    assert v["roles_validated"] == 4
    print(f"  ✅ spec table byte-for-byte: 4 roles validated")

    # ── Accessors return spec values ────────────────────────────────
    assert get_primary_interface("Executive") == "React SPA + Mobile"
    assert get_primary_interface("Manager")   == "React SPA"
    assert get_primary_interface("Staff")     == "React SPA"
    assert get_primary_interface("Admin")     == "Streamlit"
    print(f"  ✅ get_primary_interface returns spec literals")

    # ── Secondary: spec "None" → Python None for Admin ──────────────
    assert get_secondary_interface("Executive") == "Streamlit"
    assert get_secondary_interface("Manager")   == "Streamlit"
    assert get_secondary_interface("Staff")     == "Mobile"
    assert get_secondary_interface("Admin")     is None
    print(f"  ✅ get_secondary_interface: Admin maps spec 'None' → None")

    # ── Unknown role returns None (no silent default) ────────────────
    assert get_primary_interface("Hacker")   is None
    assert get_secondary_interface("Hacker") is None
    assert get_primary_interface("")         is None
    assert get_primary_interface(None)       is None    # type: ignore
    print(f"  ✅ unknown role → None (no privilege escalation)")

    # ── interface_for_user: device hint resolution for Executive ─────
    exec_user = {"role": "Executive"}
    assert interface_for_user(exec_user, device_hint="mobile")  == "Mobile"
    assert interface_for_user(exec_user, device_hint="desktop") == "React SPA"
    assert interface_for_user(exec_user)                         == "React SPA"
    print(f"  ✅ interface_for_user: Executive resolves by device_hint")

    # ── Manager/Staff/Admin: device hint ignored (single primary) ────
    assert interface_for_user({"role": "Manager"}, device_hint="mobile") == "React SPA"
    assert interface_for_user({"role": "Staff"},   device_hint="mobile") == "React SPA"
    assert interface_for_user({"role": "Admin"})                         == "Streamlit"
    print(f"  ✅ non-Executive roles: device_hint ignored")

    # ── interface_for_user: missing/invalid user → None ──────────────
    assert interface_for_user(None) is None
    assert interface_for_user({}) is None
    assert interface_for_user({"role": "Hacker"}) is None
    assert interface_for_user("not a dict") is None    # type: ignore
    print(f"  ✅ missing/invalid user → None")

    # ── all_interfaces_for_role flattens composite primary ───────────
    assert all_interfaces_for_role("Executive") == ["React SPA", "Mobile", "Streamlit"]
    assert all_interfaces_for_role("Manager")   == ["React SPA", "Streamlit"]
    assert all_interfaces_for_role("Staff")     == ["React SPA", "Mobile"]
    assert all_interfaces_for_role("Admin")     == ["Streamlit"]
    print(f"  ✅ all_interfaces_for_role expands composite + drops None")

    # ── all_interfaces_for_role unknown role → [] ────────────────────
    assert all_interfaces_for_role("Hacker") == []
    print(f"  ✅ unknown role → []")

    # ── Constants exposed ────────────────────────────────────────────
    assert INTERFACE_REACT_SPA == "React SPA"
    assert INTERFACE_MOBILE    == "Mobile"
    assert INTERFACE_STREAMLIT == "Streamlit"
    print(f"  ✅ interface name constants exposed")

    print("\n  ALL TESTS PASSED")
