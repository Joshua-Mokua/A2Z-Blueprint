#!/usr/bin/env python3
"""Seed starter productivity weights + daily target into branch_log_config.json.

The config file does not exist, so every productivity index computes to 0. This writes a
coherent starting set you can tune in Administration > Daily Log.

MODEL
  - Acquisition / revenue activities score highest.
  - High-volume, low-unit-value activities (transactions, customers served) score small
    so they don't swamp the index.
  - AMOUNT fields (KES) are entered here as points per KES 100,000 and STORED SCALED
    (weight = points / 100000), because compute_index is a flat sum(count x weight) —
    otherwise a KES 500k deposit would score 500,000 points.
  - Complaints RECEIVED = 0 (not the logger's fault; neither reward nor punish).
  - Teller errors = NEGATIVE (an error should pull the index down).

Fields are matched by LABEL (case-insensitive substring) against the live schema, so it
works regardless of internal key names. Anything unmatched is reported and left at 0.

    python seed_daily_log_weights.py            # dry run — prints the full table
    python seed_daily_log_weights.py --apply
"""
import json, shutil, sys, time
from pathlib import Path

DAILY_TARGET = 25
AMOUNT_SCALE = 100000

# label fragment -> points (per unit; for amount fields, per KES 100,000)
POINTS = [
    ("accounts opened",            5),
    ("reactivated",                4),
    ("transactions processed",     0.2),
    ("cards issued",               2),
    ("dfs",                        3),
    ("mobile money",               3),
    ("loans referred",             3),
    ("loans disbursed",            2),      # amount
    ("deposits mobilised",         2),      # amount
    ("bancassurance",              4),
    ("complaints received",        0),      # deliberately neutral
    ("complaints resolved",        3),
    ("digital transactions",       0.5),
    ("sales leads",                2),
    ("cross-sell",                 3),
    ("cross sell",                 3),
    ("teller errors",             -3),      # penalty
    ("customers served",           0.3),
    ("nps",                        1),
]

from utils.branch_log import fields_schema, load_log_config

fields = fields_schema()
print(f"live schema: {len(fields)} fields\n")

weights = {}
rows = []
unmatched = []
for f in fields:
    key   = f.get("key")
    label = str(f.get("label", "")).lower()
    ftype = str(f.get("type", "int")).lower()
    if ftype == "text":
        continue  # not weightable
    pts = None
    for frag, p in POINTS:
        if frag in label:
            pts = p; break
    if pts is None:
        unmatched.append(f"{key} ({f.get('label')})")
        pts = 0
    stored = (pts / AMOUNT_SCALE) if ftype == "amount" else pts
    weights[key] = stored
    rows.append((f.get("label"), ftype, pts, stored))

w = max(len(r[0]) for r in rows) if rows else 20
print(f"{'ACTIVITY'.ljust(w)}  TYPE    ENTERED      STORED")
print("-" * (w + 34))
for label, ftype, pts, stored in rows:
    note = " /100k" if ftype == "amount" else ""
    print(f"{str(label).ljust(w)}  {ftype:6}  {str(pts)+note:>10}  {stored:>10.6g}")

print(f"\ndaily_index_target: {DAILY_TARGET}")
if unmatched:
    print(f"\nunmatched (left at 0 — set manually if needed):")
    for u in unmatched:
        print(f"   {u}")

if "--apply" not in sys.argv:
    print("\n[DRY-RUN] re-run with --apply to write branch_log_config.json")
    sys.exit(0)

cfg_path = Path("data/branch_log_config.json")
if cfg_path.exists():
    shutil.copy2(cfg_path, cfg_path.with_suffix(f".json.pre_seed_{int(time.time())}"))
cfg = load_log_config() or {}
cfg["activity_weights"]   = weights
cfg["daily_index_target"] = DAILY_TARGET
cfg.setdefault("extra_activities", [])
cfg_path.write_text(json.dumps(cfg, indent=2), encoding="utf-8")
print(f"\nwrote {cfg_path}")
print("Restart the API server. Productivity index now computes; check Daily Log > Ranking.")
