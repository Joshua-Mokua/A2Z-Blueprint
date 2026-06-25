#!/usr/bin/env python3
"""scripts/apply_phase_a_fix.py — Phase A FIX: atomic sequence-based deal ids.

The first Phase A cut derived ids with SELECT MAX(id)+1 in app code. That has a
read-then-write gap: N concurrent creates read the same MAX, derive the SAME id,
then collide — and the id-based rollback deletes the winner. Confirmed by
stress_concurrency: duplicate ids fixed, but creates still collapsed to ~0.

This fix:
  1. _next_deal_id_from_pg() now uses nextval('pipeline_deal_seq') — atomic,
     collision-free, no read-then-write gap. (Run create_deal_id_sequence.py
     FIRST to create the sequence.)
  2. Falls back to nothing-clever: if the sequence is missing, returns None and
     the caller uses the JSON len()+1 path (dev/no-PG only).

Idempotent + backs up with .pre_phaseAfix. Dry-run by default.
    python scripts/apply_phase_a_fix.py
    python scripts/apply_phase_a_fix.py --apply
"""
from __future__ import annotations
import argparse, os, shutil, sys
from datetime import datetime

API = os.path.join("utils", "api.py")

# Anchor = the MAX-based body shipped by apply_phase_a.py.
OLD = '''    if not _db_available():
        return None
    try:
        from utils.db import db as _db
        mx = _db.fetch_scalar(
            "SELECT COALESCE(MAX(CAST(NULLIF(regexp_replace(id, '\\\\D', '', 'g'), '') AS BIGINT)), 0) "
            "FROM pipeline_deals", ())
        n = int(mx or 0) + 1
        return f"D{n:04d}"
    except Exception as e:
        logger.warning(f"_next_deal_id_from_pg failed ({e}); falling back to JSON id scheme")
        return None'''

NEW = '''    if not _db_available():
        return None
    try:
        from utils.db import db as _db
        # Atomic, collision-free id from a Postgres SEQUENCE. nextval() hands
        # every concurrent caller a DISTINCT value with no read-then-write gap,
        # so two simultaneous creates can never derive the same id (the flaw in
        # the MAX(id)+1 approach). Requires pipeline_deal_seq — create it once
        # with scripts/create_deal_id_sequence.py. If the sequence is missing,
        # fall back to the JSON scheme (dev / no-PG); never silently reuse MAX.
        n = _db.fetch_scalar("SELECT nextval('pipeline_deal_seq')", ())
        if n is None:
            return None
        return f"D{int(n):04d}"
    except Exception as e:
        logger.warning(f"_next_deal_id_from_pg (nextval) failed ({e}); "
                       f"falling back to JSON id scheme. Did you run "
                       f"create_deal_id_sequence.py?")
        return None'''

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not os.path.exists(API):
        print(f"FATAL: {API} not found — run from project root."); sys.exit(2)
    txt = open(API, encoding="utf-8").read()

    if "SELECT nextval('pipeline_deal_seq')" in txt:
        print("[ALREADY APPLIED] _next_deal_id_from_pg already uses nextval. No-op.")
        return
    c = txt.count(OLD)
    if c == 0:
        print("!! ANCHOR NOT FOUND — is apply_phase_a.py applied? (the MAX-based body)")
        print("   No file written. Paste this back if unexpected.")
        sys.exit(1)
    if c > 1:
        print(f"!! anchor found {c}x (ambiguous). No file written."); sys.exit(1)

    print("[will apply] swap _next_deal_id_from_pg MAX(id)+1 -> nextval(sequence)")
    if not args.apply:
        print("\n[DRY-RUN] No file written. Re-run with --apply.")
        return
    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(API, f"{API}.pre_phaseAfix_{ts}")
    txt = txt.replace(OLD, NEW, 1)
    tmp = API + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(txt); fh.flush(); os.fsync(fh.fileno())
    os.replace(tmp, API)
    print(f"\nApplied. Backup: {API}.pre_phaseAfix_{ts}")
    print("Restart API, then re-run stress_concurrency.py (expect Probe 1 lost-creates -> 0).")

if __name__ == "__main__":
    main()
