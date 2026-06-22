#!/usr/bin/env python3
"""
rename_directors_config.py — rename the two director role strings in the tracked
CONFIG json files only. Prose files are excluded; code files are hand-edited.

  'Director Retail Banking'     -> 'Director Consumer & Commercial Banking (CCB)'
  'Director Commercial Banking' -> 'Director Corporate & Investment Banking (CIB)'

ONLY these config files are touched (they hold genuine role-string references):
  kpi_library.json, kpi_ownership_map.json, org_hierarchy_config.json,
  role_skill_matrix.json, sbu_pnl.json, target_cascade.json

EXPLICITLY EXCLUDED (contain 'Director Retail' as PROSE, not a role):
  board_papers.json, strategic_initiatives.json, strategy_lessons.json

The replacement is whole-string and ORDER-SAFE: the longer 'Director Retail
Banking' is replaced first, so no bare 'Director Retail' fragments are created.
Bare 'Director Retail' (no 'Banking') is NEVER touched by this script.

SAFE: dry-run unless --apply. Backs up each file (.pre_dirrename_<ts>) first.

    python scripts\\rename_directors_config.py            # dry-run
    python scripts\\rename_directors_config.py --apply    # backup + rewrite
"""
import sys
from pathlib import Path
from datetime import datetime

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
DATA = Path(__file__).resolve().parent.parent / "data"

TARGETS = [
    "kpi_library.json", "kpi_ownership_map.json", "org_hierarchy_config.json",
    "role_skill_matrix.json", "sbu_pnl.json", "target_cascade.json",
]
EXCLUDED = {"board_papers.json", "strategic_initiatives.json", "strategy_lessons.json"}

# Order matters: longest first so 'Director Retail Banking' is consumed before
# any bare 'Director Retail' could match. (We don't rename bare retail at all,
# but this guards against accidental partials.)
RENAMES = [
    ("Director Retail Banking", "Director Consumer & Commercial Banking (CCB)"),
    ("Director Commercial Banking", "Director Corporate & Investment Banking (CIB)"),
]


def main():
    apply = "--apply" in sys.argv
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    total = 0
    for name in TARGETS:
        p = DATA / name
        if name in EXCLUDED:
            print(f"  SKIP (prose): {name}")
            continue
        if not p.exists():
            print(f"  missing: {name}")
            continue
        txt = p.read_text(encoding="utf-8")
        before = txt
        counts = {}
        for old, new in RENAMES:
            c = txt.count(old)
            if c:
                txt = txt.replace(old, new)
                counts[old] = c
        n = sum(counts.values())
        total += n
        if n:
            detail = ", ".join(f"{k.split()[1]}={v}" for k, v in counts.items())
            print(f"  {name}: {n} replaced ({detail})")
        else:
            print(f"  {name}: 0 (nothing to rename)")
        if apply and txt != before:
            backup = p.with_name(f"{name}.pre_dirrename_{ts}")
            backup.write_text(before, encoding="utf-8")
            p.write_text(txt, encoding="utf-8")

    print(f"\nTotal replacements: {total}")
    if not apply:
        print("[DRY-RUN] No files written. Re-run with --apply to back up + rewrite.")
    else:
        print("[APPLIED] Config role strings renamed. Code files still need hand-editing.")


if __name__ == "__main__":
    main()
