#!/usr/bin/env python3
"""scripts/apply_b2_default_to_16.py — Phase B2 of branch reconciliation.

Neutralize the hardcoded 35-branch literal in utils/core.py::DEFAULT_ORG_CONFIG
so that NO reset/seed path can ever re-clobber the 16 (the June-26 regression).
Replaces the 35-branch block with the canonical 16 (matching B1's shape, no
region tier) and clears the stale geographic `regions` key.

This closes the Rule N1 violation: the default no longer carries a different
tenant branch structure than what's configured.

SAFE: backs up utils/core.py (.pre_b2). Idempotent. --revert restores it.
Run:  python scripts\\apply_b2_default_to_16.py [--dry-run] [--revert]
"""
import re, sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "utils" / "core.py"
BAK = CORE.with_suffix(".py.pre_b2")
MARKER = "# B2: branches default reconciled to canonical 16"

# Build the 16-branch default block (same 16 as B1, Head Office first).
BRANCHES = ["Head Office", "Eldoret", "Fortis Office Park", "Industrial Area",
            "Karatina", "Karen", "Kisii", "Kisumu", "Mombasa Moi Avenue",
            "Nakuru", "Nyeri", "Plaza", "Thika", "Towers", "Upper Hill",
            "Valley Arcade", "Westlands"]

def _block():
    lines = ['    # B2: branches default reconciled to canonical 16 (no region tier).',
             '    # Branches roll up directly to Head of Branches; DSA regions are separate.',
             '    "branches": [']
    for i, nm in enumerate(BRANCHES, 1):
        is_ho = (nm == "Head Office")
        reg = "Head Office" if is_ho else "Head of Branches"
        typ = "HO" if is_ho else "Branch"
        tier = 1 if is_ho else 2
        lines.append(
            f'        {{"code":"BRN{i:03d}","name":"{nm}", "region":"{reg}", '
            f'"county":"", "type":"{typ}", "tier":{tier}}},')
    lines.append('    ],')
    lines.append('    "regions": ["Head Office", "Head of Branches"],')
    return "\n".join(lines)

# Match from the '"branches": [' line through the '"regions": [...]' line.
PATTERN = re.compile(
    r'    "branches": \[\n.*?\n    \],\n    "regions": \[[^\]]*\],',
    re.DOTALL)


def revert():
    if BAK.exists():
        shutil.copy2(BAK, CORE); BAK.unlink(); print("  reverted core.py from .pre_b2")
    else:
        print("  no .pre_b2 backup found")


def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    s = CORE.read_text(encoding="utf-8")
    if MARKER in s:
        print("  B2 already applied — nothing to do."); return
    m = PATTERN.search(s)
    if not m:
        print("  ERROR: could not locate the DEFAULT_ORG_CONFIG branches+regions block."); sys.exit(1)
    # Safety: ensure we matched the DEFAULT block (35-branch literal contains BRN035)
    if "BRN035" not in m.group(0):
        print("  ERROR: matched block does not contain BRN035 — refusing (wrong match)."); sys.exit(1)
    new = _block()
    if dry:
        print("  --dry-run: would replace this many chars:", len(m.group(0)))
        print("  new block preview (first 6 lines):")
        print("\n".join(new.splitlines()[:6]))
        print("  ...")
        return
    if not BAK.exists():
        BAK.write_text(s, encoding="utf-8")
    s2 = s[:m.start()] + new + s[m.end():]
    CORE.write_text(s2, encoding="utf-8")
    print("  replaced DEFAULT_ORG_CONFIG branches (35 -> 16) + cleared geographic regions")
    print("  backup: utils/core.py.pre_b2")


if __name__ == "__main__":
    main()
