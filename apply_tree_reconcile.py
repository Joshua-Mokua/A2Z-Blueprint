#!/usr/bin/env python3
"""scripts/apply_tree_reconcile.py — CA3b: reconcile REPORTING_TREE to the real
staff register (additive; structure unchanged).

The reporting tree used role spellings that don't exist in the staff register, so
Chief Credit / Legal / Operations chiefs' CASCADE views were wrong (their real
subordinates weren't recognised). This extends the relevant chiefs' tree_roles with
the register's actual role names and permits the "Head Office" unit (where all HO
staff sit) — the role filter keeps it scoped, since visibility = Role AND Unit. Also
adds the missing "Head of Operations" and "Head of Treasury" chief entries (they had
NO tree config -> self-only visibility).

WHO-REPORTS-TO-WHOM IS UNCHANGED — this only makes the tree recognise real role names.

SAFE: .pre_treerec backup on core.py. Idempotent. --revert.
"""
import sys, shutil
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
CORE = ROOT / "utils" / "core.py"
BAK = CORE.with_suffix(".py.pre_treerec")

# (anchor line, replacement) — each extends tree_roles + units additively.
EDITS = [
    # Chief Credit — add register credit roles + Head Office unit
    (
        '    "Chief Credit Officer":       {"tree_roles":["Chief Credit Officer","Credit Analyst","Credit Administrator"],"units":["Credit"]},',
        '    "Chief Credit Officer":       {"tree_roles":["Chief Credit Officer","Credit Analyst","Credit Administrator",'
        '"Credit Admin Officer","Assistant Manager -Credit Administration","Manager-Credit Monitoring",'
        '"Supervisor Credit Reporting","Senior Manager -Credit Analysis"],"units":["Credit","Head Office"]},',
    ),
    # Chief Compliance / Legal — add register legal roles + Head Office
    (
        '    "Chief Compliance Officer":   {"tree_roles":["Chief Compliance Officer","Compliance Officer","Legal Counsel"],"units":["Compliance & Legal"]},',
        '    "Chief Compliance Officer":   {"tree_roles":["Chief Compliance Officer","Compliance Officer","Legal Counsel",'
        '"Company Secretary and Chief Legal Officer","Manager- Legal","Legal Officer","Regulatory Compliance Officer",'
        '"Senior Manager- Compliance"],"units":["Compliance & Legal","Head Office"]},',
    ),
    # Chief Operations — add register ops roles + Head Office
    (
        '    "Chief Operations Officer":   {"tree_roles":["Chief Operations Officer","Operations Manager","Branch Operations Manager"],"units":["Operations"]},',
        '    "Chief Operations Officer":   {"tree_roles":["Chief Operations Officer","Chief Operating Officer","Operations Manager","Branch Operations Manager",'
        '"Head of Operations","Operations Officer","Operations Supervisor-DFS","Manager Card Operations",'
        '"Trade Finance Operations Officer"],"units":["Operations","Head Office"]},',
    ),
]

# New chief entries (had NO tree config). Insert after Chief Credit line.
NEW_ENTRIES = '''    "Head of Operations":         {"tree_roles":["Head of Operations","Operations Officer","Operations Supervisor-DFS","Manager Card Operations","Branch Operations Manager","Trade Finance Operations Officer"],"units":["Operations","Head Office"]},
    "Head of Treasury":           {"tree_roles":["Head of Treasury","Senior Manager Treasury","Treasury Dealer","Treasury Front Office Officer","Manager Forex Trader","Corporate Sales Dealer"],"units":["Treasury","Head Office"]},
    "Manager- Legal":             {"tree_roles":["Manager- Legal","Legal Officer"],"units":["Compliance & Legal","Head Office"]},
'''

def patch(s):
    changed = False
    for anchor, repl in EDITS:
        if anchor in s and repl not in s:
            s = s.replace(anchor, repl, 1); changed = True
    # add the new chief entries right after the (now-extended) Chief Credit line
    marker = '"units":["Credit","Head Office"]},'
    if marker in s and '"Head of Operations":' not in s:
        s = s.replace(marker, marker + "\n" + NEW_ENTRIES.rstrip(), 1); changed = True
    return s, changed

def revert():
    if BAK.exists():
        shutil.copy2(BAK, CORE); BAK.unlink(); print("  reverted core.py")
    else:
        print("  no .pre_treerec backup")

def main():
    if "--revert" in sys.argv:
        revert(); return
    dry = "--dry-run" in sys.argv
    s = CORE.read_text(encoding="utf-8")
    new, ch = patch(s)
    print(f"  core.py REPORTING_TREE: {'change' if ch else 'skip (already applied?)'}")
    if dry:
        print("  --dry-run: nothing written."); return
    if ch:
        if not BAK.exists(): BAK.write_text(s, encoding="utf-8")
        CORE.write_text(new, encoding="utf-8")
    print("  applied. Restart API.")

if __name__ == "__main__":
    main()
