# CHANGELOG v10.555 — Hardening H4: CEO/MD all-deals visibility

get_visible_staff grants full-roster visibility only to is_admin /
"admin" in role / role in _ALL_VIEW_ROLES. _ALL_VIEW_ROLES was
{"managing director","admin"} — but the canonical top role is
"Chief Executive & Managing Director", so the CEO fell through to
self-only visibility and could not see all deals. H4 adds the canonical
CEO role (+ variants) to _ALL_VIEW_ROLES (utils/core.py).
Verified: CEO/MD/Admin -> all; Branch Manager -> scoped (unchanged).
