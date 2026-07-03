#!/usr/bin/env python3
"""scripts/apply_hierarchy_react.py — wire the React Reporting Hierarchy editor.

- writes frontend/web/src/pages/HierarchyAdmin.tsx (from bundled copy)
- api.ts: fetchHierarchy / saveHierarchy + HierarchyResponse type
- App.tsx: import + route /admin/hierarchy
- Sidebar.tsx: nav item under Reference & Admin

Run from repo root. Bundled page must sit at scripts/_hierarchy_page.tsx
(the kit places it there). SAFE: .pre_hier_ui backups. Idempotent. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "frontend" / "web" / "src"
PAGE_OUT = WEB / "pages" / "HierarchyAdmin.tsx"
PAGE_SRC = Path(__file__).resolve().parent / "_hierarchy_page.tsx"
API_TS = WEB / "lib" / "api.ts"
APP = WEB / "App.tsx"
SIDEBAR = WEB / "components" / "Sidebar.tsx"

API_BLOCK = '''
// reporting hierarchy (role -> parent roles)
export interface HierarchyResponse {
  roles: string[];
  hierarchy: Record<string, string[]>;
  top: string[];
}
export async function fetchHierarchy(): Promise<HierarchyResponse> {
  return getJson<HierarchyResponse>('/admin/hierarchy');
}
export async function saveHierarchy(
  body: { action: string; role?: string; parents?: string[]; new_name?: string },
): Promise<{ status: string; hierarchy: Record<string, string[]> }> {
  return postJson<{ status: string; hierarchy: Record<string, string[]> }, typeof body>(
    '/admin/hierarchy', body);
}
'''

def revert():
    for f in (API_TS, APP, SIDEBAR):
        b = f.with_suffix(f.suffix + ".pre_hier_ui")
        if b.exists():
            shutil.copy2(b, f); b.unlink(); print(f"  reverted {f.name}")
    if PAGE_OUT.exists():
        PAGE_OUT.unlink(); print("  removed HierarchyAdmin.tsx")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv

    # 1. page file
    page_needed = not PAGE_OUT.exists()
    # 2. api.ts
    a = API_TS.read_text(encoding="utf-8")
    a_ch = "fetchHierarchy" not in a
    # 3. App.tsx
    app = APP.read_text(encoding="utf-8")
    app_ch = "HierarchyAdmin" not in app
    # 4. Sidebar
    sb = SIDEBAR.read_text(encoding="utf-8")
    sb_ch = "/admin/hierarchy" not in sb

    print(f"  HierarchyAdmin.tsx: {'write' if page_needed else 'exists'}")
    print(f"  api.ts: {'add fetchers' if a_ch else 'present'}")
    print(f"  App.tsx route: {'add' if app_ch else 'present'}")
    print(f"  Sidebar nav: {'add' if sb_ch else 'present'}")
    if dry:
        print("  --dry-run: nothing written."); return

    if page_needed:
        shutil.copy2(PAGE_SRC, PAGE_OUT)

    if a_ch:
        b = API_TS.with_suffix(API_TS.suffix + ".pre_hier_ui")
        if not b.exists(): b.write_text(a, encoding="utf-8")
        API_TS.write_text(a.rstrip() + "\n" + API_BLOCK + "\n", encoding="utf-8")

    if app_ch:
        b = APP.with_suffix(APP.suffix + ".pre_hier_ui")
        if not b.exists(): b.write_text(app, encoding="utf-8")
        # import after RolesAdmin import
        app2 = app.replace("import RolesAdmin from './pages/RolesAdmin';",
                           "import RolesAdmin from './pages/RolesAdmin';\nimport HierarchyAdmin from './pages/HierarchyAdmin';", 1)
        # route after the roles route
        app2 = app2.replace('<Route path="/admin/roles" element={<RolesAdmin />} />',
                            '<Route path="/admin/roles" element={<RolesAdmin />} />\n                    <Route path="/admin/hierarchy" element={<HierarchyAdmin />} />', 1)
        APP.write_text(app2, encoding="utf-8")

    if sb_ch:
        b = SIDEBAR.with_suffix(SIDEBAR.suffix + ".pre_hier_ui")
        if not b.exists(): b.write_text(sb, encoding="utf-8")
        # add a nav entry mirroring the Role Registry one
        anchor = "        path: '/admin/roles', label: 'Role Registry',\n        matchActive: (p) => p.startsWith('/admin/roles'),"
        if anchor in sb:
            # insert a sibling entry right after the roles entry's closing brace.
            # We mimic the same object shape; find the end of this object.
            new_entry = anchor + "\n      },\n      {\n        path: '/admin/hierarchy', label: 'Reporting Hierarchy',\n        matchActive: (p) => p.startsWith('/admin/hierarchy'),"
            sb2 = sb.replace(anchor, new_entry, 1)
            SIDEBAR.write_text(sb2, encoding="utf-8")
        else:
            print("  WARN: Sidebar anchor not found; add nav entry manually")

    print("  applied. Run TSC gate before commit.")

if __name__ == "__main__":
    main()
