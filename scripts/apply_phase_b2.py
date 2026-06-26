#!/usr/bin/env python3
"""scripts/apply_phase_b2.py — PG migration Phase B, Step 2 (read-primacy flip).

Flip _get_or_hydrate_deal from JSON-first to POSTGRES-first.

WHY THIS IS NOW SAFE (it regressed on the first attempt):
  The first Phase B attempt flipped this read while _db_sync was an INCOMPLETE
  mirror, so PG-authoritative reads dropped fields (bsc_credit_to,
  manager_override_note, ...) -> portfolio harness regressions. B0 made _db_sync
  persist all 17 fields and _normalize lift them; B1 verified the round-trip
  (create-time hard gaps = 0; all lifecycle fields confirmed in the lift list).
  PG is now a COMPLETE mirror, so reading PG-first no longer loses data.

WHAT THIS FIXES:
  Under concurrency the JSON store (rewritten whole-file, non-atomically on every
  mutation) is read mid-corruption, so the detail/scope read returns a deal with
  a clobbered staff_code -> the cascade-scope check denies a deal the caller in
  fact owns -> spurious 403 "outside your cascade scope" on concurrent updates
  (diag_concurrent_update: 7/10 403s). Postgres reads are atomic and consistent,
  so the scope check operates on clean data.

MECHANICS:
  - Read the row from Postgres first. If found, normalise it and register it on
    the request-scoped PipelineManager (replacing any stale JSON copy of the same
    id so pm.get_deal is unambiguous) so update_deal/update_stage mutate the
    PG-sourced record. Mutations still re-sync via _db_sync_pipeline_deal.
  - Fall back to the in-memory JSON store ONLY when Postgres is unavailable or the
    row is absent (dev / no-PG / brand-new-in-request deals not yet flushed).

This changes read ORDER only. Writes are unchanged (still dual JSON+PG); the
atomic-write fixes for the create-500s and lost-update race are B3/B4.

GATING (both required):
  - python scripts/simulate_credit_chain.py     -> must stay 295/295
  - python scripts/diag_concurrent_update.py     -> 403s should clear / drop sharply
  - python scripts/stress_concurrency.py         -> no NEW concurrency regressions

Idempotent + backs up .pre_phaseB2. Dry-run by default.
    python scripts/apply_phase_b2.py
    python scripts/apply_phase_b2.py --apply
"""
from __future__ import annotations
import argparse, os, shutil, sys
from datetime import datetime

API = os.path.join("utils", "api.py")

OLD = '''    deal = pm.get_deal(deal_id)
    if deal:
        return deal
    if _db_available():
        try:
            from utils.db import db as _db
            row = _db.fetch_one("SELECT * FROM pipeline_deals WHERE id = %s", (deal_id,))
            if row:
                hydrated = _normalize_db_deal_row(_serialize(row))
                try:
                    pm.deals.append(hydrated)  # register for in-request mutation
                except Exception:
                    pass
                return hydrated
        except Exception as e:
            logger.error(f"Pipeline deal hydrate failed for {deal_id}: {e}")
    return None'''

NEW = '''    # Phase B2: POSTGRES-FIRST. The JSON store is rewritten whole-file and
    # non-atomically on every mutation, so under concurrency a JSON read can
    # return a deal with clobbered fields (e.g. a blanked staff_code), which then
    # fails the cascade-scope check -> spurious 403s, and feeds stale data into
    # mutations. Postgres reads are atomic and authoritative, and B0 made it a
    # complete field mirror (verified by B1), so detail + mutation routes resolve
    # the deal from PG when available, registering it on the request-scoped
    # PipelineManager (replacing any stale JSON copy of the same id) so
    # update_deal/update_stage mutate the PG-sourced record. Falls back to the
    # JSON store only when Postgres is unavailable or the row is absent.
    if _db_available():
        try:
            from utils.db import db as _db
            row = _db.fetch_one("SELECT * FROM pipeline_deals WHERE id = %s", (deal_id,))
            if row:
                hydrated = _normalize_db_deal_row(_serialize(row))
                try:
                    # Drop any stale JSON copy of this id, then register the
                    # PG-sourced record for in-request mutation.
                    pm.deals = [d for d in pm.deals if d.get("id") != deal_id]
                    pm.deals.append(hydrated)
                except Exception:
                    pass
                return hydrated
        except Exception as e:
            logger.error(f"Pipeline deal hydrate (PG-first) failed for {deal_id}: {e}")
    # Postgres unavailable or row absent -> JSON fallback.
    deal = pm.get_deal(deal_id)
    if deal:
        return deal
    return None'''

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not os.path.exists(API):
        print(f"FATAL: {API} not found — run from project root."); sys.exit(2)
    txt = open(API, encoding="utf-8").read()

    if "Phase B2: POSTGRES-FIRST" in txt:
        print("[ALREADY APPLIED] B2 already in place. No-op."); return

    c = txt.count(OLD)
    if c == 0:
        print("!! ANCHOR NOT FOUND — _get_or_hydrate_deal body differs from expectation.")
        print("   Confirm HEAD is aab93a7 (B0) and the function is unmodified.")
        sys.exit(1)
    if c > 1:
        print(f"!! anchor {c}x (ambiguous). No file written."); sys.exit(1)

    print("[will apply] flip _get_or_hydrate_deal to Postgres-first")
    if not args.apply:
        print("\n[DRY-RUN] No file written. Re-run with --apply."); return

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(API, f"{API}.pre_phaseB2_{ts}")
    txt = txt.replace(OLD, NEW, 1)
    tmp = API + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(txt); fh.flush(); os.fsync(fh.fileno())
    os.replace(tmp, API)
    print(f"\nApplied B2. Backup: {API}.pre_phaseB2_{ts}")
    print("Restart API, then run BOTH gates:")
    print("  python scripts/simulate_credit_chain.py     (must stay 295/295)")
    print("  python scripts/diag_concurrent_update.py     (403s should clear)")
    print("  python scripts/stress_concurrency.py         (no new regressions)")

if __name__ == "__main__":
    main()
