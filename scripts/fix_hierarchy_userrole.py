#!/usr/bin/env python3
"""scripts/fix_hierarchy_userrole.py — fix the useRole destructuring in
HierarchyAdmin.tsx (TS2339). useRole() returns {user, isAdmin}, not {role}.
Mirrors the working StaffAdmin pattern (user?.role). Idempotent. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
PAGE = ROOT / "frontend" / "web" / "src" / "pages" / "HierarchyAdmin.tsx"
BAK = PAGE.with_suffix(".tsx.pre_userrolefix")

OLD = """  const { role, isAdmin } = useRole();
  const canAdmin = useMemo(() => {
    if (isAdmin) return true;
    const r = (role ?? '').toLowerCase();
    return ['admin', 'director', 'chief', 'managing'].some((t) => r.includes(t));
  }, [role, isAdmin]);"""

NEW = """  const { user, isAdmin } = useRole();
  const canAdmin = useMemo(() => {
    if (isAdmin) return true;
    const r = (user?.role ?? '').toLowerCase();
    return ['admin', 'director', 'chief', 'managing'].some((t) => r.includes(t));
  }, [user, isAdmin]);"""

def main():
    if "--revert" in sys.argv:
        if BAK.exists():
            shutil.copy2(BAK, PAGE); BAK.unlink(); print("  reverted")
        else:
            print("  no backup")
        return
    s = PAGE.read_text(encoding="utf-8")
    if NEW in s:
        print("  already fixed."); return
    if OLD not in s:
        print("  ERROR: expected useRole block not found (manual check needed)"); sys.exit(1)
    if "--dry-run" in sys.argv:
        print("  --dry-run: would fix useRole destructuring."); return
    if not BAK.exists():
        BAK.write_text(s, encoding="utf-8")
    PAGE.write_text(s.replace(OLD, NEW, 1), encoding="utf-8")
    print("  fixed useRole: {role} -> {user}, user?.role. Re-run TSC.")

if __name__ == "__main__":
    main()
