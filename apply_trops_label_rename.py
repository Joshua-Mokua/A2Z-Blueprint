#!/usr/bin/env python3
"""scripts/apply_trops_label_rename.py — 4b-0: rename user-facing "Troops
Disbursement" label -> "Trops Disbursement".

LABEL-ONLY. Leaves /troops route, Troops component, TroopsFlow types, and the
/credit-admin/troops API namespace untouched (renaming those breaks bookmarks
and API with no user-facing benefit).

Changes the 5 display strings:
  Sidebar.tsx: label 'Troops Disbursement'
  Troops.tsx : 2 breadcrumb labels + 2 titles

SAFE: .pre_trops backups. Idempotent. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
WEB = ROOT / "frontend" / "web" / "src"
SIDEBAR = WEB / "components" / "Sidebar.tsx"
PAGE = WEB / "pages" / "Troops.tsx"

def _swap(path: Path, replacements: list):
    s = path.read_text(encoding="utf-8")
    orig = s
    for old, new in replacements:
        s = s.replace(old, new)
    return s, (s != orig), orig

def revert():
    for f in (SIDEBAR, PAGE):
        b = f.with_suffix(f.suffix + ".pre_trops")
        if b.exists():
            shutil.copy2(b, f); b.unlink(); print(f"  reverted {f.name}")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv

    sb_new, sb_ch, sb_orig = _swap(SIDEBAR, [
        ("label: 'Troops Disbursement'", "label: 'Trops Disbursement'"),
    ])
    pg_new, pg_ch, pg_orig = _swap(PAGE, [
        ("label: 'Troops Disbursement'", "label: 'Trops Disbursement'"),
        ('title="Troops Disbursement"', 'title="Trops Disbursement"'),
    ])
    print(f"  Sidebar.tsx: {'change' if sb_ch else 'skip'}")
    print(f"  Troops.tsx:  {'change' if pg_ch else 'skip'}")
    if dry:
        print("  --dry-run: nothing written."); return
    if sb_ch:
        b = SIDEBAR.with_suffix(SIDEBAR.suffix + ".pre_trops")
        if not b.exists(): b.write_text(sb_orig, encoding="utf-8")
        SIDEBAR.write_text(sb_new, encoding="utf-8")
    if pg_ch:
        b = PAGE.with_suffix(PAGE.suffix + ".pre_trops")
        if not b.exists(): b.write_text(pg_orig, encoding="utf-8")
        PAGE.write_text(pg_new, encoding="utf-8")
    print("  applied. Run TSC gate.")

if __name__ == "__main__":
    main()
