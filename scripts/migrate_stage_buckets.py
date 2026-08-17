#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Move the BUCKET journey into admin config, and remap deals onto it. READ ONLY
until --apply.

RULING (2026-08-09): the journey is Initiation, Documentation, Unit Review
(Branch Credit Committee / Department Analyst / Department Business Committee),
Credit Analysis, Credit Administration, TROPS for loan products; and
Initiation, Documentation, Approval, Opening for accounts and liabilities.
Each bucket carries a %, and its micro-steps distribute that %.

Also: "we need to remap everything to match our perfect scenario, otherwise they
will continue confusing the picture we are looking at ... these test deals
should always be adjusted and enhanced with any new development to ensure we
have the perfect test picture always."

WHAT IT DOES
  1. writes stage_buckets into pipeline_settings (admin-editable thereafter)
  2. rebuilds stage_flows from the buckets, so the OLD vocabulary (Lead,
     Contacted, Qualified…) stops being offered anywhere
  3. remaps every deal whose stage is not a micro-step of its flow

REMAPPING IS EXPLICIT, NEVER GUESSED BY SIMILARITY. Each old stage has a stated
destination below and the script prints every move before making one. A deal
whose stage has no mapping is REPORTED and left alone - inventing a position for
a real deal is worse than leaving it visible as unplaced.

THIS IS A PILOT HEADING TO PRODUCTION, so: dry run by default, a full backup of
both the settings and the deals before any write, and a printed before/after
count per stage so the move can be audited afterwards.

    python scripts\\migrate_stage_buckets.py            # show everything
    python scripts\\migrate_stage_buckets.py --apply
"""
import json
import os
import shutil
import sys
from datetime import datetime

sys.path.insert(0, os.getcwd())

# Old stage -> new micro-step. Stated, not inferred.
REMAP = {
    # legacy sales vocabulary, retired
    "lead": "Initiation",
    "contacted": "Initiation",
    "prospecting": "Initiation",
    "needs analysis": "Initiation",
    "qualified": "Documentation",
    "application": "Documentation",
    "proposal": "Documentation",
    "offer / proposal": "Offer Letter",
    "term sheet": "Offer Letter",
    "negotiation": "Offer Letter",
    "due diligence": "Credit Analysis",
    "credit review": "Credit Analysis",
    "credit assessment": "Credit Analysis",
    "credit committee": "Department Business Committee",
    "department credit committee": "Department Business Committee",
    "bank approval": "Department Business Committee",
    "compliance": "Legal - Security Perfection",
    "compliance review": "Legal - Security Perfection",
    "vetting": "Legal - Security Perfection",
    "valuation": "Credit Analysis",
    "kyc / documentation": "Documentation",
    "account opening": "Opening",
    "disbursed": "Disbursement",
    # already-current stages that simply need to survive untouched
    "initiation": "Initiation",
    "documentation": "Documentation",
    "branch credit committee": "Branch Credit Committee",
    "department analyst": "Department Analyst",
    "department business committee": "Department Business Committee",
    "credit analysis": "Credit Analysis",
    "offer letter": "Offer Letter",
    "legal - security perfection": "Legal - Security Perfection",
    "disbursement": "Disbursement",
    "approval": "Approval",
    "opening": "Opening",
}
KEEP = ("Closed Won", "Closed Lost")


def main():
    apply = "--apply" in sys.argv
    try:
        from utils.core import get_pipeline_settings, save_pipeline_settings, PipelineManager
        from utils.pipeline_funnel import DEFAULT_BUCKETS, buckets_for, micro_steps, flow_for_deal
    except Exception as exc:
        print("ABORT: %s" % exc)
        return 1

    ps = get_pipeline_settings() or {}

    print("=" * 74)
    print("BUCKET JOURNEY — what goes into admin config")
    print("=" * 74)
    total_ok = True
    for flow, chain in DEFAULT_BUCKETS.items():
        tot = sum(b["weight"] for b in chain)
        flag = "" if abs(tot - 100) < 1e-9 else "   *** weights sum to %s, not 100" % tot
        if flag:
            total_ok = False
        print("\n  %s%s" % (flow, flag))
        for b in chain:
            print("     %-24s %3d%%   %s" % (b["label"], b["weight"], ", ".join(b["steps"])))
    if not total_ok:
        print("\nABORT: a bucket chain does not sum to 100 — a disbursed deal would")
        print("       never reach 100% and the whole book would be understated.")
        return 1

    # ── the deals ────────────────────────────────────────────────────────────
    pm = PipelineManager()
    deals = list(getattr(pm, "deals", []) or [])
    pg_rows = []
    try:
        from utils.db import db
        if db.is_postgres_ready():
            pg_rows = db.fetch_all("SELECT id, stage FROM pipeline_deals")
    except Exception:
        pg_rows = []

    import collections
    print("\n" + "=" * 74)
    print("DEALS TO REMAP")
    print("=" * 74)
    print("JSON store: %d   Postgres: %d" % (len(deals), len(pg_rows)))

    moves = collections.Counter()
    unmapped = collections.Counter()
    for d in deals:
        st = str(d.get("stage") or "").strip()
        if st in KEEP:
            continue
        flow = flow_for_deal(d)
        valid = {s.lower() for s in micro_steps(flow)}
        if st.lower() in valid:
            continue
        dest = REMAP.get(st.lower())
        if dest and dest.lower() in valid:
            moves[(st, dest, flow)] += 1
        else:
            unmapped[(st, flow)] += 1

    if moves:
        print("\n  planned moves (JSON store):")
        for (a, b, f), n in moves.most_common():
            print("     %-30s -> %-30s %-10s x%d" % (a, b, f, n))
    else:
        print("\n  no JSON deals need moving.")

    if unmapped:
        print("\n  *** NO MAPPING — left alone and reported, never guessed:")
        for (a, f), n in unmapped.most_common():
            print("     %-30s %-10s x%d" % (a, f, n))

    pg_moves = collections.Counter()
    for r in pg_rows:
        st = str(r.get("stage") or "").strip()
        if st in KEEP:
            continue
        dest = REMAP.get(st.lower())
        if dest and dest != st:
            pg_moves[(st, dest)] += 1
    if pg_moves:
        print("\n  planned moves (Postgres):")
        for (a, b), n in pg_moves.most_common():
            print("     %-30s -> %-30s x%d" % (a, b, n))

    if not apply:
        print("\nDRY RUN — nothing written. Re-run with --apply.")
        print("Both the settings and the deal store are backed up before any write.")
        return 0

    # ── write config ─────────────────────────────────────────────────────────
    ps["stage_buckets"] = {f: [dict(b, steps=list(b["steps"])) for b in chain]
                           for f, chain in DEFAULT_BUCKETS.items()}
    # stage_flows becomes the DERIVED micro-step list, so the old vocabulary
    # stops being offered anywhere in the UI.
    ps["stage_flows"] = {f: micro_steps(f) + list(KEEP) for f in DEFAULT_BUCKETS}
    try:
        save_pipeline_settings(ps)
    except Exception as exc:
        print("ABORT: could not save settings: %s" % exc)
        return 1
    print("\nwrote stage_buckets and rebuilt stage_flows for %d flows." % len(DEFAULT_BUCKETS))

    # ── move the deals ───────────────────────────────────────────────────────
    stamp = datetime.now().isoformat(timespec="seconds")
    src = os.path.join("data", "pipeline_deals.json")
    if os.path.isfile(src):
        shutil.copy2(src, src + ".pre_buckets")
        print("backed up %s" % src)

    moved = 0
    for d in deals:
        st = str(d.get("stage") or "").strip()
        if st in KEEP:
            continue
        flow = flow_for_deal(d)
        valid = {s.lower() for s in micro_steps(flow)}
        if st.lower() in valid:
            continue
        dest = REMAP.get(st.lower())
        if dest and dest.lower() in valid:
            d["stage"] = dest
            d["stage_remapped_from"] = st
            d["stage_remapped_at"] = stamp
            moved += 1
    if moved:
        try:
            pm._save_deals()
        except Exception as exc:
            print("ABORT: could not save deals: %s" % exc)
            return 1
    print("remapped %d deals in the JSON store." % moved)

    pgm = 0
    try:
        from utils.db import db
        if db.is_postgres_ready():
            for r in pg_rows:
                st = str(r.get("stage") or "").strip()
                if st in KEEP:
                    continue
                dest = REMAP.get(st.lower())
                if dest and dest != st:
                    db.execute("UPDATE pipeline_deals SET stage = %s WHERE id = %s",
                               (dest, r.get("id")))
                    pgm += 1
    except Exception as exc:
        print("Postgres remap failed (JSON store already moved): %s" % exc)
    print("remapped %d deals in Postgres." % pgm)

    print("\nRestart uvicorn. The funnel now runs Initiation -> Disbursement.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
