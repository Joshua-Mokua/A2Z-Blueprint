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


# ── Register-staff branch test chain (self-healed, like the canonical set) ──
# These are REAL staff_register people (300xxx) for one branch (Thika),
# frontline → CEO, used for scope testing. They're listed here so
# UserManager.ensure_branch_test_logins() can restore them after any users.json
# reset — the same "express" persistence the canonical logins have. can_view_all
# is False for everyone except the register root (CEO), so cascade scope is
# exercised honestly (deal scope is role-based regardless, but we keep the flag
# correct). Password = EcoStaff + last-4 of staff_code.
# (username, password, full_name, role, staff_code, unit, region, can_view_all)
BranchTestLogin = Tuple[str, str, str, str, str, str, str, bool]

_BRANCH_TEST_LOGINS: List[BranchTestLogin] = [
    ("oscar0720",      "EcoStaff0720", "Oscar Abdullahi",    "Teller",                               "300720", "Thika",       "Mt Kenya West", False),
    ("gilbert0724",    "EcoStaff0724", "Gilbert Wanjala",    "Customer Service Officer",             "300724", "Thika",       "Mt Kenya West", False),
    ("frank0731",      "EcoStaff0731", "Frank Wanyama",      "Relationship Officer-Personal Banker", "300731", "Thika",       "Mt Kenya West", False),
    ("isaac0718",      "EcoStaff0718", "Isaac Mugambi",      "Branch Operations Supervisor",         "300718", "Thika",       "Mt Kenya West", False),
    ("vincent0728",    "EcoStaff0728", "Vincent Mohamed",    "Branch Relationship Manager",          "300728", "Thika",       "Mt Kenya West", False),
    ("zachary0717",    "EcoStaff0717", "Zachary Baya",       "Branch Operations Manager",            "300717", "Thika",       "Mt Kenya West", False),
    ("immaculate0716", "EcoStaff0716", "Immaculate Njoroge", "Senior Branch Manager",                "300716", "Thika",       "Mt Kenya West", False),
    ("beatrice1501",   "EcoStaff1501", "Beatrice Musyoka",   "Area Manager",                         "301501", "Head Office", "Head Office",   False),
    ("veronica1500",   "EcoStaff1500", "Veronica Mutai",     "Head of Branches",                     "301500", "Head Office", "Head Office",   False),
    ("nicholas0002",   "EcoStaff0002", "Nicholas Ndegwa",    "Chief Retail Banking Officer",         "300002", "Head Office", "Head Office",   False),
    ("william0001",    "EcoStaff0001", "William Mwanake",    "Chief Executive & Managing Director",  "300001", "Head Office", "Head Office",   True),
]


def branch_test_logins() -> List[BranchTestLogin]:
    """Return the register-staff branch test chain (Thika, frontline → CEO)."""
    return list(_BRANCH_TEST_LOGINS)
