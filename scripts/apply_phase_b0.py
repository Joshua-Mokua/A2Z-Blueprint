#!/usr/bin/env python3
"""scripts/apply_phase_b0.py — PG migration Phase B, Step 0 (write completeness).

PURELY ADDITIVE. Makes Postgres a COMPLETE mirror of a pipeline deal so that a
future read-primacy flip (B2) cannot drop fields. Two coordinated edits:

  EDIT 1 (_db_sync_pipeline_deal metadata block): PERSIST the fields that are set
    on a deal but were never written to PG. These silently vanish under any
    PG-authoritative read (the cause of the Phase-B portfolio regressions:
    bsc_credit_to / manager_override_note were never in PG at all).

  EDIT 2 (_normalize_db_deal_row lift tuple): READ BACK every one of those fields
    (plus the 4 that were written but not lifted: portfolio_owner_code,
    portfolio_owner_name, is_ntb, source), so DB-first list/analytics/detail all
    reconstruct the full deal.

This changes NO read order and NO concurrency behavior. It only writes more to PG
and reads more back. Harness must stay 295/295 (additive). After this lands, B1
(round-trip verification probe) then B2 (read-primacy flip) become safe.

Fields persisted/lifted by this step (the audit gap):
  bsc_credit_to, manager_override_note, is_referral, referred_at,
  accepted_by, accepted_at, declined_by, declined_at,
  disbursed, disbursed_at, disbursed_under_override,
  override_approved, override_approved_by, win_probability,
  credit_deferred_to, credit_deferred_to_code, history
  + lift-only (already written): portfolio_owner_code, portfolio_owner_name,
    is_ntb, source

Idempotent + backs up .pre_phaseB0. Dry-run by default.
    python scripts/apply_phase_b0.py
    python scripts/apply_phase_b0.py --apply
"""
from __future__ import annotations
import argparse, os, shutil, sys
from datetime import datetime

API = os.path.join("utils", "api.py")

# ── EDIT 1: append missing fields to the _db_sync metadata block ───────────────
# Anchor: the closing lines of the metadata dict.
SYNC_OLD = '''                "sla_step_log":         deal.get("sla_step_log"),
                "sla_commitments":      deal.get("sla_commitments"),
            }),'''

SYNC_NEW = '''                "sla_step_log":         deal.get("sla_step_log"),
                "sla_commitments":      deal.get("sla_commitments"),
                # Phase B0: persist the remaining deal fields so PG is a COMPLETE
                # mirror (these were JSON-only and vanished under PG-first reads).
                "bsc_credit_to":            deal.get("bsc_credit_to"),
                "manager_override_note":    deal.get("manager_override_note"),
                "is_referral":              deal.get("is_referral"),
                "referred_at":              deal.get("referred_at"),
                "accepted_by":              deal.get("accepted_by"),
                "accepted_at":              deal.get("accepted_at"),
                "declined_by":              deal.get("declined_by"),
                "declined_at":              deal.get("declined_at"),
                "disbursed":                deal.get("disbursed"),
                "disbursed_at":             deal.get("disbursed_at"),
                "disbursed_under_override": deal.get("disbursed_under_override"),
                "override_approved":        deal.get("override_approved"),
                "override_approved_by":     deal.get("override_approved_by"),
                "win_probability":          deal.get("win_probability"),
                "credit_deferred_to":       deal.get("credit_deferred_to"),
                "credit_deferred_to_code":  deal.get("credit_deferred_to_code"),
                "history":                  deal.get("history"),
            }),'''

# ── EDIT 2: extend the _normalize lift tuple to read all of them back ──────────
NORM_OLD = '''                   "referral_status", "referred_to_code", "referred_to",
                   "referred_by_code", "referred_by_name", "referral_note",
                   "decline_reason", "sla_step_log", "sla_commitments"):'''

NORM_NEW = '''                   "referral_status", "referred_to_code", "referred_to",
                   "referred_by_code", "referred_by_name", "referral_note",
                   "decline_reason", "sla_step_log", "sla_commitments",
                   # Phase B0: lift the full field set back so DB-first reads
                   # reconstruct a complete deal (write side in _db_sync).
                   "portfolio_owner_code", "portfolio_owner_name", "is_ntb",
                   "source", "bsc_credit_to", "manager_override_note",
                   "is_referral", "referred_at", "accepted_by", "accepted_at",
                   "declined_by", "declined_at", "disbursed", "disbursed_at",
                   "disbursed_under_override", "override_approved",
                   "override_approved_by", "win_probability",
                   "credit_deferred_to", "credit_deferred_to_code", "history"):'''

EDITS = [
    (API, "_db_sync: persist 17 missing fields",  SYNC_OLD, SYNC_NEW),
    (API, "_normalize: lift full field set back", NORM_OLD, NORM_NEW),
]

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--apply", action="store_true")
    args = ap.parse_args()
    if not os.path.exists(API):
        print(f"FATAL: {API} not found — run from project root."); sys.exit(2)
    txt = open(API, encoding="utf-8").read()

    if '"bsc_credit_to":            deal.get("bsc_credit_to")' in txt:
        print("[ALREADY APPLIED] B0 fields already in _db_sync. No-op."); return

    plan = []
    for _path, label, old, new in EDITS:
        c = txt.count(old)
        if c == 1:   plan.append((label, "will apply"))
        elif c == 0: plan.append((label, "!! ANCHOR NOT FOUND"))
        else:        plan.append((label, f"!! anchor {c}x (ambiguous)"))
    print("Phase B0 patch plan:")
    for label, status in plan:
        print(f"  [{status:22s}] {label}")
    if any(s.startswith("!!") for _, s in plan):
        print("\nABORT: anchor problem. No file written.")
        print("(Run on the committed Phase A state — git checkout utils/api.py first.)")
        sys.exit(1)
    if not args.apply:
        print("\n[DRY-RUN] No file written. Re-run with --apply."); return

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copy2(API, f"{API}.pre_phaseB0_{ts}")
    for _path, _label, old, new in EDITS:
        txt = txt.replace(old, new, 1)
    tmp = API + ".tmp"
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(txt); fh.flush(); os.fsync(fh.fileno())
    os.replace(tmp, API)
    print(f"\nApplied B0. Backup: {API}.pre_phaseB0_{ts}")
    print("Restart API, run the harness (must stay 295/295 — additive only).")

if __name__ == "__main__":
    main()
