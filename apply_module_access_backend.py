#!/usr/bin/env python3
"""scripts/apply_module_access_backend.py — module-level access in Staff Admin.

1. Adds GET /api/admin/modules -> the canonical module list (key + label)
   from utils.core.MODULE_ACCESS, so the React modal can render checkboxes.
2. Extends the staff PATCH to accept accessible_modules (jsonb list), writing
   it to the existing users.accessible_modules column.

SAFE: backs up utils/api.py (.pre_modaccess). Idempotent. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "utils" / "api.py"
BAK = API.with_suffix(".py.pre_modaccess")
EP_MARKER = "# === MODULE ACCESS LIST ENDPOINT ==="

EP_BLOCK = '''

# === MODULE ACCESS LIST ENDPOINT ===
@app.get("/api/admin/modules", tags=["admin"])
def list_access_modules(user: dict = Depends(require_config_admin)):
    """Canonical module list for the Staff Admin module-access picker.
    Returns [{key, label, default_roles}] from utils.core.MODULE_ACCESS."""
    try:
        from utils.core import MODULE_ACCESS
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"module registry unavailable: {exc}")
    out = []
    for key, cfg in MODULE_ACCESS.items():
        out.append({
            "key": key,
            "label": key.replace("_", " ").title(),
            "min": cfg.get("min", ""),
        })
    return {"modules": out}
# === END MODULE ACCESS LIST ENDPOINT ===
'''

# Extend PATCH: add accessible_modules handling. Anchor on the existing col_map
# block and inject jsonb handling right before the "if not cols" guard.
PATCH_ANCHOR = '''    cols, vals = [], []
    for col, val in col_map.items():
        if val is not None:
            cols.append(f"{col} = %s"); vals.append(val)
    if not cols:'''

PATCH_NEW = '''    cols, vals = [], []
    for col, val in col_map.items():
        if val is not None:
            cols.append(f"{col} = %s"); vals.append(val)
    # accessible_modules (jsonb) — module-level access grant. Stored as a JSON
    # array of module keys. Empty list = explicit "no extra modules" (role
    # default still applies at read time via MODULE_ACCESS).
    if getattr(payload, "accessible_modules", None) is not None:
        import json as _json_mod
        cols.append("accessible_modules = %s")
        vals.append(_json_mod.dumps(list(payload.accessible_modules)))
    if not cols:'''


def revert():
    if BAK.exists():
        shutil.copy2(BAK, API); BAK.unlink(); print("  reverted api.py from .pre_modaccess")
    else:
        print("  no .pre_modaccess backup found")


def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    s = API.read_text(encoding="utf-8")

    # 1. Add accessible_modules to the _StaffPatch model
    model_changed = False
    if "class _StaffPatch" in s and "accessible_modules" not in s.split("class _StaffPatch")[1].split("class ")[0]:
        # inject field into _StaffPatch
        import re
        m = re.search(r'(class _StaffPatch\(BaseModel\):\n(?:.*\n)*?)(\n\n|\nclass )', s)
        if m:
            block = m.group(1)
            new_block = block.rstrip() + "\n    accessible_modules: Optional[list] = None\n"
            s = s.replace(block, new_block, 1)
            model_changed = True

    ep_changed = EP_MARKER not in s
    patch_changed = PATCH_ANCHOR in s

    print(f"  _StaffPatch.accessible_modules: {'added' if model_changed else 'present/skip'}")
    print(f"  /api/admin/modules endpoint: {'will add' if ep_changed else 'present'}")
    print(f"  PATCH accessible_modules handling: {'will add' if patch_changed else 'anchor MISSING'}")

    if dry:
        print("  --dry-run: nothing written."); return
    if not BAK.exists():
        BAK.write_text(s, encoding="utf-8")
    if patch_changed:
        s = s.replace(PATCH_ANCHOR, PATCH_NEW, 1)
    if ep_changed:
        s = s.rstrip() + "\n" + EP_BLOCK + "\n"
    API.write_text(s, encoding="utf-8")
    print("  applied. Restart API.")


if __name__ == "__main__":
    main()
