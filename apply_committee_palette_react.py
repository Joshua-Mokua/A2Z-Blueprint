#!/usr/bin/env python3
"""scripts/apply_committee_palette_react.py — 4b-1 React: committee palette admin.

- writes pages/CommitteeAdmin.tsx (bundled)
- api.ts: CommitteeDef type + fetchCommitteePalette/upsertCommittee/
  deleteCommittee/seedCommitteePalette
- App.tsx: import + route /admin/committees
- Sidebar.tsx: nav entry under Reference & Admin

SAFE: .pre_cmte_ui backups. Idempotent. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "frontend" / "web" / "src"
PAGE_OUT = WEB / "pages" / "CommitteeAdmin.tsx"
PAGE_SRC = Path(__file__).resolve().parent / "_committee_page.tsx"
API_TS = WEB / "lib" / "api.ts"
APP = WEB / "App.tsx"
SIDEBAR = WEB / "components" / "Sidebar.tsx"

API_BLOCK = '''
// credit committee palette (4b-1)
export interface CommitteeMemberDef { name: string; role: string; }
export interface CommitteeDef {
  code: string;
  name: string;
  chaired_by?: string;
  recording_mode: string;
  voting_rule: string;
  amount_threshold_kes: number;
  members: CommitteeMemberDef[];
}
export interface CommitteePaletteResponse {
  committees: CommitteeDef[];
  recording_modes: string[];
  voting_rules: string[];
}
export async function fetchCommitteePalette(): Promise<CommitteePaletteResponse> {
  return getJson<CommitteePaletteResponse>('/admin/committee-palette');
}
export async function upsertCommittee(committee: CommitteeDef): Promise<{ status: string; committees: CommitteeDef[] }> {
  return postJson<{ status: string; committees: CommitteeDef[] }, { committee: CommitteeDef }>(
    '/admin/committee-palette', { committee });
}
export async function deleteCommittee(code: string): Promise<{ status: string; committees: CommitteeDef[] }> {
  return postJson<{ status: string; committees: CommitteeDef[] }, { delete: string }>(
    '/admin/committee-palette', { delete: code });
}
export async function seedCommitteePalette(): Promise<{ status: string; committees: CommitteeDef[] }> {
  return postJson<{ status: string; committees: CommitteeDef[] }, Record<string, never>>(
    '/admin/committee-palette/seed', {});
}
'''

def revert():
    for f in (API_TS, APP, SIDEBAR):
        b = f.with_suffix(f.suffix + ".pre_cmte_ui")
        if b.exists():
            shutil.copy2(b, f); b.unlink(); print(f"  reverted {f.name}")
    if PAGE_OUT.exists():
        PAGE_OUT.unlink(); print("  removed CommitteeAdmin.tsx")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv

    page_needed = not PAGE_OUT.exists()
    a = API_TS.read_text(encoding="utf-8"); a_ch = "fetchCommitteePalette" not in a
    app = APP.read_text(encoding="utf-8"); app_ch = "CommitteeAdmin" not in app
    sb = SIDEBAR.read_text(encoding="utf-8"); sb_ch = "/admin/committees" not in sb

    print(f"  CommitteeAdmin.tsx: {'write' if page_needed else 'exists'}")
    print(f"  api.ts: {'add' if a_ch else 'present'}")
    print(f"  App.tsx: {'add' if app_ch else 'present'}")
    print(f"  Sidebar: {'add' if sb_ch else 'present'}")
    if dry:
        print("  --dry-run: nothing written."); return

    if page_needed:
        shutil.copy2(PAGE_SRC, PAGE_OUT)
    if a_ch:
        b = API_TS.with_suffix(API_TS.suffix + ".pre_cmte_ui")
        if not b.exists(): b.write_text(a, encoding="utf-8")
        API_TS.write_text(a.rstrip() + "\n" + API_BLOCK + "\n", encoding="utf-8")
    if app_ch:
        b = APP.with_suffix(APP.suffix + ".pre_cmte_ui")
        if not b.exists(): b.write_text(app, encoding="utf-8")
        app2 = app.replace("import HierarchyAdmin from './pages/HierarchyAdmin';",
                           "import HierarchyAdmin from './pages/HierarchyAdmin';\nimport CommitteeAdmin from './pages/CommitteeAdmin';", 1)
        app2 = app2.replace('<Route path="/admin/hierarchy" element={<HierarchyAdmin />} />',
                            '<Route path="/admin/hierarchy" element={<HierarchyAdmin />} />\n                    <Route path="/admin/committees" element={<CommitteeAdmin />} />', 1)
        APP.write_text(app2, encoding="utf-8")
    if sb_ch:
        b = SIDEBAR.with_suffix(SIDEBAR.suffix + ".pre_cmte_ui")
        if not b.exists(): b.write_text(sb, encoding="utf-8")
        anchor = "        path: '/admin/hierarchy', label: 'Reporting Hierarchy',\n        matchActive: (p) => p.startsWith('/admin/hierarchy'),"
        if anchor in sb:
            new_entry = anchor + "\n        visibleFor: (_isMgr, _isAdmin, isConfigAdmin) => isConfigAdmin,\n      },\n      {\n        path: '/admin/committees', label: 'Credit Committees',\n        matchActive: (p) => p.startsWith('/admin/committees'),"
            SIDEBAR.write_text(sb.replace(anchor, new_entry, 1), encoding="utf-8")
        else:
            print("  WARN: Sidebar anchor not found; add nav entry manually")
    print("  applied. Run TSC gate.")

if __name__ == "__main__":
    main()
