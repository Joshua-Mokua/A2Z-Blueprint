#!/usr/bin/env python3
"""scripts/apply_committee_members_react.py — C3a React: committee member staff_code.

Committee members in the admin editor gain a Staff code field, so they can be
notified + record a pre-read (C3b). Extends CommitteeMemberDef + the CommitteeAdmin
member editor rows.

SAFE: .pre_members_ui backups. Idempotent. --revert. TSC-gated.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
API = ROOT / "frontend" / "web" / "src" / "lib" / "api.ts"
ADMIN = ROOT / "frontend" / "web" / "src" / "pages" / "CommitteeAdmin.tsx"

def patch_api(s):
    if "staff_code" in s.split("CommitteeMemberDef")[1].split("}")[0]: return s, False
    return s.replace("export interface CommitteeMemberDef { name: string; role: string; }",
                     "export interface CommitteeMemberDef { name: string; role: string; staff_code?: string; }", 1), True

def patch_admin(s):
    if "Staff code" in s: return s, False
    s = s.replace("  function setMember(i: number, field: 'name' | 'role', value: string) {",
                  "  function setMember(i: number, field: 'name' | 'role' | 'staff_code', value: string) {", 1)
    s = s.replace(
        "onClick={() => setDraft({ ...draft, members: [...(draft.members ?? []), { name: '', role: '' }] })}>",
        "onClick={() => setDraft({ ...draft, members: [...(draft.members ?? []), { name: '', role: '', staff_code: '' }] })}>", 1)
    s = s.replace(
        '''                    <input className="w-1/2 rounded border px-2 py-1.5 text-sm" placeholder="Name" value={m.name}
                      onChange={(e) => setMember(i, 'name', e.target.value)} />
                    <input className="w-1/2 rounded border px-2 py-1.5 text-sm" placeholder="Role" value={m.role}
                      onChange={(e) => setMember(i, 'role', e.target.value)} />''',
        '''                    <input className="w-1/3 rounded border px-2 py-1.5 text-sm" placeholder="Name" value={m.name}
                      onChange={(e) => setMember(i, 'name', e.target.value)} />
                    <input className="w-1/3 rounded border px-2 py-1.5 text-sm" placeholder="Role" value={m.role}
                      onChange={(e) => setMember(i, 'role', e.target.value)} />
                    <input className="w-1/3 rounded border px-2 py-1.5 text-sm" placeholder="Staff code" value={m.staff_code ?? ''}
                      onChange={(e) => setMember(i, 'staff_code', e.target.value)} />''', 1)
    s = s.replace('<p className="text-sm font-medium">Members (name + role, for the audit trail)</p>',
                  '<p className="text-sm font-medium">Members (name + role + staff code — staff code lets them be notified & record a pre-read)</p>', 1)
    return s, True

def revert():
    for f in (API, ADMIN):
        b = f.with_suffix(f.suffix + ".pre_members_ui")
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
            b = f.with_suffix(f.suffix + ".pre_members_ui")
            if not b.exists(): b.write_text(f.read_text(encoding="utf-8"), encoding="utf-8")
            f.write_text(new, encoding="utf-8")
    print("  applied. Run TSC gate.")

if __name__ == "__main__":
    main()
