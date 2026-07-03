#!/usr/bin/env python3
"""scripts/apply_md_convening_react.py — C4 React: MD convening queue page.

Adds a Committee Convening page (referred cases grouped by tier, pre-read tallies,
Convene action) + fetchers + route + nav link.

- api.ts: convening fetchers + AppSla import (multi-line-safe)
- pages/CommitteeConvening.tsx: the page (written whole)
- App.tsx: import + route
- Sidebar.tsx: nav link under Credit

SAFE: .pre_convene_ui backups. Idempotent. --revert. TSC-gated.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "frontend" / "web" / "src" / "lib" / "api.ts"
PAGE = ROOT / "frontend" / "web" / "src" / "pages" / "CommitteeConvening.tsx"
APP = ROOT / "frontend" / "web" / "src" / "App.tsx"
SIDEBAR = ROOT / "frontend" / "web" / "src" / "components" / "Sidebar.tsx"
PAGE_SRC = Path(__file__).resolve().parent.parent / "CommitteeConvening.tsx"

def patch_api(s):
    if "fetchConveningQueue" in s: return s, False
    # AppSla import — multi-line-safe: insert before the closing brace of the
    # types/lms import.
    if "AppSla" not in s:
        close = "} from '@/types/lms';"
        if close in s:
            s = s.replace(close, "  AppSla,\n" + close, 1)
    block = '''
// C4: MD convening queue
export interface ConveningCase {
  id: string; client_name?: string; product?: string; amount?: number;
  pre_read_count: number; pre_read_tally: Record<string, number>;
  convened: boolean; sla?: AppSla | null;
}
export interface ConveningTier { tier: number | null; name: string | null; count: number; cases: ConveningCase[]; }
export interface ConveningQueueResponse { tiers: ConveningTier[]; total: number; awaiting: number; }
export async function fetchConveningQueue(): Promise<ConveningQueueResponse> {
  return getJson<ConveningQueueResponse>('/lms/committee/convening-queue');
}
export async function convokeCommittee(appId: string): Promise<LoanAppMutationResponse> {
  return postJson<LoanAppMutationResponse, Record<string, never>>(
    `/lms/applications/${encodeURIComponent(appId)}/committee/convene`, {});
}
'''
    return s.rstrip() + "\n" + block + "\n", True

def patch_app(s):
    if "CommitteeConvening" in s: return s, False
    s = s.replace("import CommitteeAdmin from './pages/CommitteeAdmin';",
                  "import CommitteeAdmin from './pages/CommitteeAdmin';\nimport { CommitteeConvening } from './pages/CommitteeConvening';", 1)
    s = s.replace('                    <Route path="/lms/:appId"  element={<LmsApplicationDetail />} />',
                  '                    <Route path="/lms/:appId"  element={<LmsApplicationDetail />} />\n'
                  '                    <Route path="/committee/convening" element={<CommitteeConvening />} />', 1)
    return s, True

def patch_sidebar(s):
    if "Committee Convening" in s: return s, False
    return s.replace(
        "      { path: '/lms', label: 'Credit Analysis', matchActive: (p) => p === '/lms' || p.startsWith('/lms/') },",
        "      { path: '/lms', label: 'Credit Analysis', matchActive: (p) => p === '/lms' || p.startsWith('/lms/') },\n"
        "      { path: '/committee/convening', label: 'Committee Convening', matchActive: (p) => p.startsWith('/committee/convening') },", 1), True

def revert():
    for f in (API, APP, SIDEBAR):
        b = f.with_suffix(f.suffix + ".pre_convene_ui")
        if b.exists():
            shutil.copy2(b, f); b.unlink(); print(f"  reverted {f.name}")
    if PAGE.exists():
        PAGE.unlink(); print("  removed CommitteeConvening.tsx")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    results = []
    for f, fn in ((API, patch_api), (APP, patch_app), (SIDEBAR, patch_sidebar)):
        new, ch = fn(f.read_text(encoding="utf-8"))
        results.append((f, new, ch)); print(f"  {f.name}: {'change' if ch else 'skip'}")
    page_needed = not PAGE.exists()
    print(f"  CommitteeConvening.tsx: {'create' if page_needed else 'exists'}")
    if dry:
        print("  --dry-run: nothing written."); return
    for f, new, ch in results:
        if ch:
            b = f.with_suffix(f.suffix + ".pre_convene_ui")
            if not b.exists(): b.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
            f.write_text(new, encoding="utf-8")
    if page_needed:
        PAGE.write_text(PAGE_SRC.read_text(encoding="utf-8"), encoding="utf-8")
    print("  applied. Run TSC gate.")

if __name__ == "__main__":
    main()
