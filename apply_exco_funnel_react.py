#!/usr/bin/env python3
"""scripts/apply_exco_funnel_react.py — C3c React: EXCO full-funnel grant toggle.

Adds an "EXCO view" checkbox per committee member in the admin editor — grants that
member full pipeline+credit funnel visibility (planning view like the MD). Intended
for EXCO-level members serving with the MD.

- api.ts: CommitteeMemberDef.full_funnel
- CommitteeAdmin.tsx: toggleFunnel + per-member EXCO-view checkbox

SAFE: .pre_exco_ui backups. Idempotent. --revert. TSC-gated.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "frontend" / "web" / "src" / "lib" / "api.ts"
ADMIN = ROOT / "frontend" / "web" / "src" / "pages" / "CommitteeAdmin.tsx"

def patch_api(s):
    if "full_funnel" in s.split("CommitteeMemberDef")[1].split("}")[0]: return s, False
    return s.replace(
        "export interface CommitteeMemberDef { name: string; role: string; staff_code?: string; }",
        "export interface CommitteeMemberDef { name: string; role: string; staff_code?: string; full_funnel?: boolean; }", 1), True

def patch_admin(s):
    if "toggleFunnel" in s: return s, False
    s = s.replace(
        '''  function setMember(i: number, field: 'name' | 'role' | 'staff_code', value: string) {
    if (!draft) return;
    const members = [...(draft.members ?? [])];
    members[i] = { ...members[i], [field]: value };
    setDraft({ ...draft, members });
  }''',
        '''  function setMember(i: number, field: 'name' | 'role' | 'staff_code', value: string) {
    if (!draft) return;
    const members = [...(draft.members ?? [])];
    members[i] = { ...members[i], [field]: value };
    setDraft({ ...draft, members });
  }
  function toggleFunnel(i: number, value: boolean) {
    if (!draft) return;
    const members = [...(draft.members ?? [])];
    members[i] = { ...members[i], full_funnel: value };
    setDraft({ ...draft, members });
  }''', 1)
    s = s.replace(
        '''                    <input className="w-1/3 rounded border px-2 py-1.5 text-sm" placeholder="Staff code" value={m.staff_code ?? ''}
                      onChange={(e) => setMember(i, 'staff_code', e.target.value)} />
                    <Button variant="ghost" size="sm"
                      onClick={() => setDraft({ ...draft, members: (draft.members ?? []).filter((_, j) => j !== i) })}>
                      x
                    </Button>''',
        '''                    <input className="w-1/4 rounded border px-2 py-1.5 text-sm" placeholder="Staff code" value={m.staff_code ?? ''}
                      onChange={(e) => setMember(i, 'staff_code', e.target.value)} />
                    <label className="flex items-center gap-1 text-xs text-gray-600 whitespace-nowrap" title="EXCO full-funnel visibility (planning view like the MD)">
                      <input type="checkbox" checked={!!m.full_funnel}
                        onChange={(e) => toggleFunnel(i, e.target.checked)} />
                      EXCO view
                    </label>
                    <Button variant="ghost" size="sm"
                      onClick={() => setDraft({ ...draft, members: (draft.members ?? []).filter((_, j) => j !== i) })}>
                      x
                    </Button>''', 1)
    return s, True

def revert():
    for f in (API, ADMIN):
        b = f.with_suffix(f.suffix + ".pre_exco_ui")
        if b.exists():
            shutil.copy2(b, f); b.unlink(); print(f"  reverted {f.name}")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    files = []
    for f, fn in ((API, patch_api), (ADMIN, patch_admin)):
        new, ch = fn(f.read_text(encoding="utf-8"))
        files.append((f, new, ch)); print(f"  {f.name}: {'change' if ch else 'skip'}")
    if dry:
        print("  --dry-run: nothing written."); return
    for f, new, ch in files:
        if ch:
            b = f.with_suffix(f.suffix + ".pre_exco_ui")
            if not b.exists(): b.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
            f.write_text(new, encoding="utf-8")
    print("  applied. Run TSC gate.")

if __name__ == "__main__":
    main()
