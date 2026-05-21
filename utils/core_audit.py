"""utils.core_audit — audit logging, access control, and approval helpers.

This module is the FIRST physically-extracted submodule from utils/core.py
in the v5.21+ decomposition effort. It now CONTAINS the implementations,
having held them as re-export shims from v5.21 through v5.24.

Pages can import via either path — both produce identical behaviour:

    NEW (preferred): from utils.core_audit import audit_log
    OLD (legacy):    from utils.core import audit_log

The OLD path still works because utils.core re-exports these symbols
from us at the bottom of its module body (the reverse of v5.21's shim).
Once every page has been migrated to the NEW path, the reverse re-exports
in utils.core can be deleted. The G14 audit gate tracks adoption.

Symbols exposed:
    Logging          : audit_log
    Approvals        : requires_dual_approval, submit_for_approval,
                       get_pending_approvals
    Department       : get_user_department, is_dept_super_user,
                       is_ict_admin, get_dept_modules
    Access           : check_access, check_page_access,
                       get_visible_staff, tab_visible_cascade,
                       fix_view_all_permissions
    Password helpers : _hash_password
"""
from __future__ import annotations

# ── Standard-library dependencies referenced by the moved functions ─────
import hashlib
import json
from datetime import datetime

# ── Module-level constants we still need from utils.core ────────────────
# These remain in core.py because they're referenced by lots of other
# code that hasn't been split out yet. core_audit reads them by import.
from utils.core import (
    DATA_DIR,
    MAKER_CHECKER_LIMITS,
    DEPT_PRIMARY_MODULES,
    UNIVERSAL_MODULES,
    MODULE_ACCESS,
    REPORTING_TREE,
    _ALL_VIEW_ROLES,
    _REGION_SCOPED_ROLES,
    _UNIT_SCOPED_ROLES,
)


# ─── audit_log (was core.py L4790–L4824) ───


# ─── AUDIT LOG ───────────────────────────────────────────────────────
def audit_log(action: str, username: str, detail: str = "",
              module: str = "", before: str = "", after: str = ""):
    """
    Append-only audit trail. Each entry is one JSON line in audit_trail.jsonl.
    The file is never rewritten — only appended — making it tamper-evident.
    Also maintains audit_log.json (last 2000) for the admin UI quick view.
    """
    import hashlib as _hl
    entry = {
        "ts":     datetime.now().isoformat(),
        "user":   username,
        "action": action,
        "detail": str(detail)[:500],
        "module": module,
        "before": str(before)[:200] if before else "",
        "after":  str(after)[:200]  if after  else "",
    }
    # ── Append-only JSONL (regulatory-grade immutable trail) ──────────
    try:
        trail_file = DATA_DIR / "audit_trail.jsonl"
        with open(str(trail_file), "a", encoding="utf-8") as _f:
            _f.write(json.dumps(entry) + "\n")
    except: pass
    # ── Rolling JSON for UI (last 2000) ───────────────────────────────
    try:
        log_file = DATA_DIR / "audit_log.json"
        raw = log_file.read_text() if log_file.exists() else "[]"
        log = json.loads(raw) if raw.strip() else []
        if not isinstance(log, list): log = []
        log.append(entry)
        log_file.write_text(json.dumps(log[-2000:], indent=2))
    except: pass

# ─── requires_dual_approval (was core.py L4869–L4873) ───

def requires_dual_approval(operation: str, amount: float) -> bool:
    """Return True if this operation+amount requires a checker."""
    limit = MAKER_CHECKER_LIMITS.get(operation, float("inf"))
    return amount >= limit

# ─── get_user_department (was core.py L4984–L4987) ───

def get_user_department(user_data: dict) -> str:
    """Return canonical department name for a user."""
    return user_data.get("department", "Retail Banking") or "Retail Banking"

# ─── is_dept_super_user (was core.py L4988–L4990) ───

def is_dept_super_user(user_data: dict) -> bool:
    return bool(user_data.get("is_dept_super_user", False))

# ─── is_ict_admin (was core.py L4991–L4993) ───

def is_ict_admin(user_data: dict) -> bool:
    return bool(user_data.get("is_ict_admin", False))

# ─── get_dept_modules (was core.py L4994–L5041) ───

def get_dept_modules(user_data: dict) -> list:
    """Return module keys visible to this user.
    Reads from org_config.json dept_module_assignments first (admin-configurable),
    falls back to hardcoded DEPT_PRIMARY_MODULES.
    """
    import json
    from pathlib import Path as _P

    dept    = get_user_department(user_data)
    admin   = user_data.get("is_admin", False)
    can_all = user_data.get("can_view_all", False)

    if admin or can_all:
        return list(DEPT_PRIMARY_MODULES.get("Executive", []))

    # 1. Try org_config.json dept_module_assignments
    try:
        _oc_path = _P(__file__).parent.parent / "data" / "org_config.json"
        if _oc_path.exists():
            _oc = json.loads(_oc_path.read_text())
            # Find dept id from dept name
            _dept_id = None
            for _d in _oc.get("departments", []):
                if _d["name"] == dept:
                    _dept_id = _d["id"]
                    break
            if _dept_id:
                _primary = _oc.get("dept_module_assignments", {}).get(_dept_id)
                if _primary:
                    extra  = user_data.get("accessible_modules", [])
                    hidden = set(user_data.get("hidden_modules", []))
                    # Apply dept_module_config hidden modules
                    _dmc_p = _P(__file__).parent.parent / "data" / "dept_module_config.json"
                    if _dmc_p.exists():
                        _dmc = json.loads(_dmc_p.read_text())
                        hidden |= set(_dmc.get(dept, {}).get("hidden_modules", []))
                    combined = list(dict.fromkeys(_primary + UNIVERSAL_MODULES + extra))
                    return [m for m in combined if m not in hidden]
    except Exception:
        pass

    # 2. Fall back to hardcoded DEPT_PRIMARY_MODULES
    primary = DEPT_PRIMARY_MODULES.get(dept, DEPT_PRIMARY_MODULES.get("Retail Banking", []))
    extra   = user_data.get("accessible_modules", [])
    hidden  = set(user_data.get("hidden_modules", []))
    combined = list(dict.fromkeys(primary + UNIVERSAL_MODULES + extra))
    return [m for m in combined if m not in hidden]

# ─── get_pending_approvals (was core.py L5042–L5050) ───



def get_pending_approvals(data_path) -> list:
    """Read pending dual-approval items."""
    import json
    from pathlib import Path
    p = Path(data_path).parent / "pending_approvals.json"
    return json.loads(p.read_text()) if p.exists() else []

# ─── submit_for_approval (was core.py L5051–L5063) ───

def submit_for_approval(item: dict, data_path) -> str:
    """Submit an item for checker approval. Returns approval ID."""
    import json, uuid
    from pathlib import Path
    p = Path(data_path).parent / "pending_approvals.json"
    items = json.loads(p.read_text()) if p.exists() else []
    approval_id = f"APR{str(uuid.uuid4())[:8].upper()}"
    item["approval_id"] = approval_id
    item["status"] = "pending_checker"
    items.append(item)
    p.write_text(json.dumps(items, indent=2))
    return approval_id

# ─── get_visible_staff (was core.py L5535–L5613) ───


def get_visible_staff(user_data: dict, staff_scores) -> "pd.DataFrame":
    """
    Return only the staff_scores rows this user is allowed to see,
    following the exact org reporting tree.
    Overall ranking is preserved from the full dataset.
    """
    import pandas as _pd
    if staff_scores is None or (hasattr(staff_scores,"__len__") and len(staff_scores)==0):
        return staff_scores

    is_admin = user_data.get("is_admin", False)
    can_all  = user_data.get("can_view_all", False)
    role     = str(user_data.get("role","")).strip()
    role_l   = role.lower()
    my_name  = user_data.get("full_name","")
    my_unit  = user_data.get("unit","")

    # Only true admins and MD see everyone — not just anyone with can_view_all
    # can_view_all is a legacy flag; tree_access is now role-based
    if is_admin or "admin" in role_l or role_l in _ALL_VIEW_ROLES:
        return staff_scores.copy()

    # Find tree config
    tree_cfg = REPORTING_TREE.get(role)
    if tree_cfg is None:
        for k in REPORTING_TREE:
            if k.lower() == role_l:
                tree_cfg = REPORTING_TREE[k]
                break

    if tree_cfg is None:
        # No tree config — self only
        self_rows = staff_scores[staff_scores["Staff Name"] == my_name].copy()
        return self_rows

    tree_roles = tree_cfg["tree_roles"]
    tree_units = tree_cfg["units"]

    # Filter by roles
    if tree_roles is None:
        visible = staff_scores.copy()
    else:
        visible = staff_scores[staff_scores["Role"].isin(tree_roles)].copy()

    # Apply scope filter
    if tree_units is not None:
        # Fixed HO unit list
        visible = visible[visible["Unit"].isin(tree_units)]

    elif role_l in _REGION_SCOPED_ROLES:
        # Regional Head — scope by Region column, not Unit
        # Determine the region this person covers from their unit name or Region field
        my_region = user_data.get("region","")
        if not my_region:
            # Derive from unit name e.g. "North Region" → "North"
            unit_parts = str(my_unit).lower().split()
            for part in ("north","central","south"):
                if part in unit_parts:
                    my_region = part.title()
                    break
        if my_region:
            # Match "North" against Region column values like "North","North Region"
            region_clean = my_region.lower().replace(" region","").strip()
            def _region_match(r):
                return str(r).lower().replace(" region","").strip() == region_clean
            visible = visible[visible["Region"].apply(_region_match)]
        # If we couldn't determine region, fall back to full tree (better than nothing)

    elif role_l in ("director retail banking","head of retail"):
        branch_units = [u for u in staff_scores["Unit"].unique() if "Branch" in str(u)]
        retail_units = ["Retail Banking"] + branch_units
        visible = visible[visible["Unit"].isin(retail_units)]

    elif role_l in _UNIT_SCOPED_ROLES and my_unit:
        visible = visible[visible["Unit"] == my_unit]

    return visible

# ─── tab_visible_cascade (was core.py L5614–L5632) ───


def tab_visible_cascade(user_data: dict, tab_name: str) -> bool:
    """Which cascade tabs should be visible for this user."""
    role    = str(user_data.get("role","")).lower()
    is_adm  = user_data.get("is_admin", False)
    can_all = user_data.get("can_view_all", False)
    is_md   = is_adm or can_all or "managing" in role or role in ("md","ceo","admin")
    is_mgr  = is_md or any(k in role for k in (
        "director","head of","regional","manager","chief"))
    return {
        # v10.410 — Consolidated top-level tabs (max 6 per Joshua's directive)
        "bank_setup":      is_md,    # MD-only: bank targets + fixed KPIs
        "cascade_alloc":   True,     # cascade alloc parent visible to all (capacity feedback inside is for all)
        "my_view":         True,     # all: my targets + strategic impact
        "team_analytics":  is_mgr,   # mgr: rollup + simulator + cascade tree
        "health":          is_mgr,   # mgr: coverage + (future) executive health
        "negotiation":     is_mgr,   # mgr: review requests with E4 escalation
        # Legacy keys retained for backward compat with any old links/audits
        "bank_targets":    is_md,
        "fixed_kpis":      is_md,
        "set_targets":     is_mgr,
        "my_targets":      True,
        "team_progress":   is_mgr,
        "strategic_impact": True,
        "what_if_simulator": is_mgr,
        "cascade_tree":    is_mgr,
        "coverage":        is_mgr,
        "review_requests": is_mgr,
        # v10.412 — Capacity Feedback (E6)
        "capacity_feedback": True,   # staff raise + managers review (UI auto-switches)
        # v10.411 — Cascade Health (E5)
        "cascade_health":  is_mgr,
    }.get(tab_name, True)

# ─── check_access (was core.py L5633–L5696) ───



def check_access(user_data: dict, module: str) -> tuple:
    """
    Check if user has access to a module.
    Checks in order: ICT module_control → admin flag → accessible_modules → role-based.
    Returns (has_access: bool, reason: str)
    """
    if not user_data:
        return False, "Not logged in"

    role     = str(user_data.get("role","")).strip()
    is_admin = user_data.get("is_admin", False)
    can_all  = user_data.get("can_view_all", False)

    # Check ICT module control (can disable modules bank-wide)
    # Admins bypass this check
    if not is_admin and not can_all and role != "Admin":
        try:
            import json
            from pathlib import Path as _P
            _mc_path = _P(__file__).parent.parent / "data" / "module_control.json"
            if _mc_path.exists():
                _mc = json.loads(_mc_path.read_text())
                if _mc.get(module, {}).get("enabled", True) is False:
                    return False, "Module disabled by ICT admin"
        except Exception:
            pass  # If file unreadable, don't block access

    # Admins always have access
    if is_admin or role == "Admin":
        return True, "Admin"

    cfg       = MODULE_ACCESS.get(module, {"min":"public","roles_all":[]})
    min_level = cfg["min"]
    roles_all = cfg["roles_all"]

    # "self" and "public" modules are ALWAYS accessible to any logged-in user
    # This must run before the accessible_modules override list check,
    # because self-level modules (pipeline, cascade, cims) should never be blocked
    if min_level in ("public","self"):
        return True, "Self/public access"

    # Check explicit module overrides on user account
    # Only applies to non-self modules — a role in roles_all also grants access
    accessible = user_data.get("accessible_modules")
    if role in roles_all:
        return True, f"Role '{role}' has access"
    if accessible is not None and len(accessible) > 0:
        if module in accessible:
            return True, "Module override granted"
        # Override list is set, role not in roles_all, module not in list
        return False, "Not in accessible_modules list"

    if min_level == "admin":
        return False, "Admin only"
    if min_level == "public":
        return True, "Public"
    role_l_ca = role.lower()
    if can_all and (is_admin or role_l_ca in _ALL_VIEW_ROLES) and min_level in ("all","team","unit","self"):
        return True, "can_view_all"

    return False, f"Role '{role}' does not have access to {module}"

# ─── check_page_access (was core.py L5697–L5709) ───




def check_page_access(user_data: dict, module: str, page: str) -> bool:
    """Check if user can access a specific page within a module."""
    if not check_access(user_data, module)[0]:
        return False
    # Check sub-page restrictions
    accessible_pages = user_data.get("accessible_pages", {})
    if module in accessible_pages and accessible_pages[module]:
        return page in accessible_pages[module]
    return True  # no sub-page restriction set — all pages visible

# ─── fix_view_all_permissions (was core.py L5710–L5724) ───


def fix_view_all_permissions(user_manager) -> int:
    """Strip can_view_all from any non-MD/Admin account. Returns count fixed."""
    MD_ROLES = {"managing director", "admin", "system admin"}
    fixed = 0
    for username, udata in user_manager.users.items():
        role_l = str(udata.get("role","")).lower()
        is_adm = bool(udata.get("is_admin", False))
        if udata.get("can_view_all") and not is_adm and role_l not in MD_ROLES:
            udata["can_view_all"] = False
            fixed += 1
    if fixed:
        user_manager.save()
    return fixed

# ─── _hash_password (was core.py L5775–L5791) ───

def _hash_password(pw: str) -> str:
    """Module-level password hashing helper.

    bcrypt with rounds=12, falls back to SHA-256 only if bcrypt is unavailable.
    Module-level so bootstrap code (UserManager._load / _defaults) can use it
    before the UserManager instance is fully constructed.

    V-003 fix — every password-creating site MUST call this rather than
    hashlib.sha256 directly. Audit gate G11 enforces this.
    """
    try:
        import bcrypt as _bc
        return _bc.hashpw(pw.encode("utf-8"), _bc.gensalt(rounds=12)).decode("utf-8")
    except ImportError:
        # Fallback only — bcrypt should always be available per requirements.txt
        return hashlib.sha256(pw.encode()).hexdigest()


__all__ = [
    "audit_log",
    "requires_dual_approval",
    "submit_for_approval",
    "get_pending_approvals",
    "get_user_department",
    "is_dept_super_user",
    "is_ict_admin",
    "get_dept_modules",
    "check_access",
    "check_page_access",
    "get_visible_staff",
    "tab_visible_cascade",
    "fix_view_all_permissions",
    "_hash_password",
]
