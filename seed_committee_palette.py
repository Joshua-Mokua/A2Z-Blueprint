#!/usr/bin/env python3
"""Seed the committee palette in lms_config.json so the admin 'Credit committee journey'
picker has options. ADDITIVE + IDEMPOTENT: only fills committee_palette if empty; touches
nothing else in lms_config.json; does NOT touch product_flows or any bank mapping.

The committees mirror the hardcoded routing codes already in the system.

    python seed_committee_palette.py            # dry run — shows what it would add
    python seed_committee_palette.py --apply
"""
import sys, json, shutil, time
from pathlib import Path

F = Path("data/lms_config.json")
cfg = json.loads(F.read_text(encoding="utf-8")) if F.exists() else {}

# canonical committees (match the hardcoded defs: BCC1, DCC_CONS/COMM/CIB, BCC2, BCC3)
PALETTE = [
    {"code": "BCC1",     "name": "Branch Credit Committee",   "kind": "branch"},
    {"code": "DCC_CONS", "name": "Consumer DCC",              "kind": "dcc"},
    {"code": "DCC_COMM", "name": "Commercial DCC",            "kind": "dcc"},
    {"code": "DCC_CIB",  "name": "CIB DCC",                   "kind": "dcc"},
    {"code": "BCC2",     "name": "Business Credit Committee", "kind": "committee"},
    {"code": "BCC3",     "name": "Board Credit Committee",    "kind": "committee"},
]

cw = cfg.get("credit_workflow")
if not isinstance(cw, dict):
    cw = {}
existing = cw.get("committee_palette")

if isinstance(existing, list) and len(existing) > 0:
    print(f"palette already has {len(existing)} entries — NOT overwriting. Nothing to do.")
    for p in existing:
        print(f"   {p.get('code')} - {p.get('name')}")
    sys.exit(0)

print("=== would seed committee_palette with: ===")
for p in PALETTE:
    print(f"   {p['code']:10} {p['name']}")
print("\n(only committee_palette is added; product_flows and all other config untouched)")

if "--apply" not in sys.argv:
    print("\n[DRY-RUN] re-run with --apply"); sys.exit(0)

# apply — preserve everything else
cw["committee_palette"] = PALETTE
cfg["credit_workflow"] = cw
shutil.copy2(F, F.with_suffix(f".json.bak_{int(time.time())}")) if F.exists() else None
F.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
print("applied. committee_palette seeded; nothing else changed.")
