"""utils/test_logins.py — canonical per-role test logins (single source of truth).

Shared by:
  - scripts/seed_test_logins.py            (bulk (re)seed + TEST_LOGINS.md key)
  - utils.core.UserManager.ensure_test_logins  (per-boot self-heal)

so the two can never drift. Derives exactly one account per canonical role
from utils.role_taxonomy. Password convention = EcoStaff + last-4 of the
account's staff_code (william001 -> EcoStaff0001).
"""
from __future__ import annotations

import re
from typing import List, Tuple

# Roles pinned to a specific username for continuity / convenience.
USERNAME_OVERRIDES = {
    "Chief Executive & Managing Director": "william001",
}
# staff_code (and thus password suffix) pinned for those usernames.
STAFFCODE_OVERRIDES = {
    "william001": "0001",  # -> EcoStaff0001
}

# (username, password, full_name, role, staff_code)
TestLogin = Tuple[str, str, str, str, str]

_CACHE: List[TestLogin] | None = None


def _slug(role: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "_", role.lower()).strip("_")
    return re.sub(r"_+", "_", s)


def _build() -> List[TestLogin]:
    from utils.role_taxonomy import list_all_classified_roles  # lazy: no cycle
    roles = sorted(
        (r.get("role") if isinstance(r, dict) else str(r))
        for r in list_all_classified_roles()
    )
    rows: List[TestLogin] = []
    nxt = 2
    for role in roles:
        username = USERNAME_OVERRIDES.get(role, _slug(role))
        if username in STAFFCODE_OVERRIDES:
            code = STAFFCODE_OVERRIDES[username]
        else:
            code = f"{nxt:04d}"
            nxt += 1
        password = "EcoStaff" + code[-4:]
        rows.append((username, password, f"Test {role}", role, code))
    return rows


def canonical_test_logins() -> List[TestLogin]:
    """Return the deterministic list of canonical test logins (cached)."""
    global _CACHE
    if _CACHE is None:
        _CACHE = _build()
    return _CACHE
