#!/usr/bin/env python3
"""scripts/apply_hierarchy_backend.py — React-editable reporting hierarchy.

Adds to utils/api.py (mirrors the /api/admin/branches pattern):
  GET  /api/admin/hierarchy  -> {roles:[...], hierarchy:{role:[parents]}, top:[roots]}
  POST /api/admin/hierarchy  -> edit a role's reporting line, add/rename/remove role.
      body actions:
        {"action":"set_parents","role":R,"parents":[...]}
        {"action":"add_role","role":R,"parents":[...]}
        {"action":"rename_role","role":R,"new_name":N}
        {"action":"remove_role","role":R}
  Cycle-checked, config-admin gated, backs up org_config, audited.

SAFE: backs up utils/api.py (.pre_hierarchy). Idempotent. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "utils" / "api.py"
BAK = API.with_suffix(".py.pre_hierarchy")
MARKER = "# === REPORTING HIERARCHY ENDPOINTS ==="

BLOCK = '''

# === REPORTING HIERARCHY ENDPOINTS ===
def _hier_has_cycle(hierarchy: dict) -> str:
    """Return a description of the first cycle found, or '' if acyclic."""
    WHITE, GREY, BLACK = 0, 1, 2
    color = {r: WHITE for r in hierarchy}
    def visit(node, stack):
        if color.get(node, WHITE) == GREY:
            return " -> ".join(stack + [node])
        if color.get(node, WHITE) == BLACK:
            return ""
        color[node] = GREY
        for parent in hierarchy.get(node, []) or []:
            if parent in hierarchy:
                c = visit(parent, stack + [node])
                if c:
                    return c
        color[node] = BLACK
        return ""
    for r in list(hierarchy.keys()):
        c = visit(r, [])
        if c:
            return c
    return ""


@app.get("/api/admin/hierarchy", tags=["admin"])
def get_admin_hierarchy(user: dict = Depends(get_current_user)):
    """Current reporting hierarchy (role -> parent roles) from org_config.
    Readable by any authenticated user."""
    from utils.core import get_org_config
    cfg = get_org_config() or {}
    hierarchy = cfg.get("hierarchy", {}) or {}
    roles = cfg.get("roles", []) or sorted(hierarchy.keys())
    top = [r for r, parents in hierarchy.items() if not parents]
    return {"roles": sorted(set(roles) | set(hierarchy.keys())),
            "hierarchy": hierarchy, "top": top}


@app.post("/api/admin/hierarchy", tags=["admin"])
def set_admin_hierarchy(payload: dict = Body(default_factory=dict),
                        user: dict = Depends(require_config_admin)):
    """Edit the reporting hierarchy. See module docstring for actions.
    Persists to org_config.json (with backup) and validates against cycles."""
    from utils.core import get_org_config, save_org_config
    action = str(payload.get("action", "")).strip()
    role = str(payload.get("role", "")).strip()
    if not action:
        raise HTTPException(status_code=400, detail="action is required")

    cfg = get_org_config() or {}
    hierarchy = dict(cfg.get("hierarchy", {}) or {})
    roles = list(cfg.get("roles", []) or sorted(hierarchy.keys()))

    if action == "set_parents":
        if role not in hierarchy and role not in roles:
            raise HTTPException(status_code=404, detail=f"role '{role}' not found")
        parents = [str(p).strip() for p in (payload.get("parents") or []) if str(p).strip()]
        for p in parents:
            if p not in hierarchy and p not in roles:
                raise HTTPException(status_code=400, detail=f"parent role '{p}' not found")
        if role in parents:
            raise HTTPException(status_code=400, detail="a role cannot report to itself")
        hierarchy[role] = parents

    elif action == "add_role":
        if not role:
            raise HTTPException(status_code=400, detail="role name required")
        if role in hierarchy or role in roles:
            raise HTTPException(status_code=409, detail=f"role '{role}' already exists")
        parents = [str(p).strip() for p in (payload.get("parents") or []) if str(p).strip()]
        for p in parents:
            if p not in hierarchy and p not in roles:
                raise HTTPException(status_code=400, detail=f"parent role '{p}' not found")
        hierarchy[role] = parents
        if role not in roles:
            roles.append(role)

    elif action == "rename_role":
        new_name = str(payload.get("new_name", "")).strip()
        if not role or not new_name:
            raise HTTPException(status_code=400, detail="role and new_name required")
        if role not in hierarchy and role not in roles:
            raise HTTPException(status_code=404, detail=f"role '{role}' not found")
        if new_name in hierarchy or new_name in roles:
            raise HTTPException(status_code=409, detail=f"'{new_name}' already exists")
        # use the atomic rename if available (renames across kpis, weights, etc.)
        try:
            from utils.core import rename_role_everywhere
            rename_role_everywhere(role, new_name)
            cfg = get_org_config() or {}
            return {"status": "renamed", "from": role, "to": new_name,
                    "hierarchy": cfg.get("hierarchy", {})}
        except Exception:
            # fallback: rename within hierarchy + roles only
            hierarchy = {(new_name if k == role else k):
                         [(new_name if p == role else p) for p in v]
                         for k, v in hierarchy.items()}
            roles = [new_name if r == role else r for r in roles]

    elif action == "remove_role":
        if role not in hierarchy and role not in roles:
            raise HTTPException(status_code=404, detail=f"role '{role}' not found")
        children = [r for r, parents in hierarchy.items() if role in (parents or [])]
        if children:
            raise HTTPException(status_code=409,
                detail=f"cannot remove '{role}': {len(children)} role(s) report to it: {children[:5]}")
        hierarchy.pop(role, None)
        roles = [r for r in roles if r != role]

    else:
        raise HTTPException(status_code=400, detail=f"unknown action '{action}'")

    cyc = _hier_has_cycle(hierarchy)
    if cyc:
        raise HTTPException(status_code=400, detail=f"change would create a cycle: {cyc}")

    cfg["hierarchy"] = hierarchy
    cfg["roles"] = roles
    try:
        from pathlib import Path as _Path
        from datetime import datetime as _dt
        import shutil as _shutil
        src = _Path(__file__).resolve().parent.parent / "data" / "org_config.json"
        if src.exists():
            _shutil.copyfile(src, src.with_suffix(f".pre_hierarchy_{_dt.now():%Y%m%d-%H%M%S}.json"))
    except Exception as _exc:
        logger.warning("hierarchy: backup snapshot failed: %s", _exc)

    save_org_config(cfg)
    _audit("API_HIERARCHY_CHANGE", user, f"{action}|{role}|{payload.get('parents') or payload.get('new_name') or ''}")
    return {"status": "saved", "action": action, "role": role, "hierarchy": hierarchy}
# === END REPORTING HIERARCHY ENDPOINTS ===
'''

def revert():
    if BAK.exists():
        shutil.copy2(BAK, API); BAK.unlink(); print("  reverted api.py from .pre_hierarchy")
    else:
        print("  no .pre_hierarchy backup found")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    s = API.read_text(encoding="utf-8")
    if MARKER in s:
        print("  already applied."); return
    new = s.rstrip() + "\n" + BLOCK + "\n"
    if dry:
        print(f"  --dry-run: would append hierarchy endpoints ({len(BLOCK)} chars). Nothing written."); return
    if not BAK.exists():
        BAK.write_text(s, encoding="utf-8")
    API.write_text(new, encoding="utf-8")
    print("  appended hierarchy endpoints (GET+POST). Restart API.")

if __name__ == "__main__":
    main()
