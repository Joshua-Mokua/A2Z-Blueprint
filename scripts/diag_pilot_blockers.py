#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Why is no branch committee set, and why is a deal stuck? READ ONLY.

TWO PILOT REPORTS (2026-08-12) that need YOUR data to answer - the committees
and the deals live on the running instance, not in the repository, so this
reports what is actually there rather than what I would guess.

    python scripts\\diag_pilot_blockers.py
    python scripts\\diag_pilot_blockers.py --deal D2989
"""
import os
import sys

sys.path.insert(0, os.getcwd())


def rule(t):
    print("\n" + "=" * 78)
    print(t)
    print("=" * 78)


def committees():
    """"We created the 16 branch committees but the admin is not able to see
    them, and thus technically no branch credit committee is set."

    Two different faults produce that sentence, and they need different fixes:
    the committees were never written, or they were written without the `kind`
    the branch filter looks for. This tells them apart.
    """
    # Read the file directly - the loader name has moved before and a
    # diagnostic that cannot run is worth nothing.
    import json
    path = os.path.join("data", "lms_config.json")
    if not os.path.isfile(path):
        print("  data/lms_config.json not found.")
        return
    with open(path, encoding="utf-8") as fh:
        cfg = json.load(fh) or {}
    cw = cfg.get("credit_workflow", {}) if isinstance(cfg, dict) else {}
    pal = cw.get("committee_palette")
    if not isinstance(pal, list):
        print("  committee_palette is MISSING from lms_config.credit_workflow.")
        print("  Nothing was ever written - the 16 did not save.")
        return
    print("  palette entries: %d" % len(pal))
    if not pal:
        print("  The palette is EMPTY. Whatever created the 16 did not persist.")
        return

    import collections
    kinds = collections.Counter(str(c.get("kind", "") or "(none)").lower() for c in pal)
    print("  by kind: %s" % dict(kinds))
    branch = [c for c in pal if str(c.get("kind", "")).lower() == "branch"]
    print("  entries with kind='branch': %d" % len(branch))

    if pal and not branch:
        print("")
        print("  *** THIS IS THE FAULT. Committees exist, but none carries")
        print("      kind='branch'. Anything that filters on branch kind - the")
        print("      branch-committee generator, and any journey that expects a")
        print("      branch gate - sees none, so 'no branch credit committee is")
        print("      set' is literally true even though the records are there.")
        print("")
        print("      Fix the kind on the 16 rather than recreating them, or")
        print("      re-run the generator which sets it:")
        print("        POST /api/admin/committee-palette/generate-branch")
    for c in pal[:8]:
        print("     %-8s %-46s kind=%s" % (str(c.get("code"))[:8],
                                           str(c.get("name"))[:46],
                                           c.get("kind") or "(none)"))
    if len(pal) > 8:
        print("     ... and %d more" % (len(pal) - 8))

    # Which products actually reference a committee gate?
    try:
        from utils.core import get_pipeline_settings
        flows = (get_pipeline_settings() or {}).get("product_flows") or {}
        codes = {str(c.get("code")) for c in pal}
        print("\n  PRODUCTS AND THEIR COMMITTEE GATES")
        for prod, e in list(flows.items())[:12]:
            j = (e or {}).get("committee_journey") or []
            bad = [g for g in j if g not in codes]
            print("     %-28s %s%s" % (prod[:28], j or "(none)",
                                       "  <-- unknown: %s" % bad if bad else ""))
    except Exception as exc:
        print("  (could not read product flows: %s)" % str(exc)[:50])


def stuck_validation(deal_id=""):
    """"The branch manager sees nothing pending validation, but the owner
    cannot close, saying it is pending validation."

    THE TWO SURFACES ASK DIFFERENT QUESTIONS.

    The OWNER is refused by the advance path: manager_validated is False, so
    no stage change - including closing - is allowed.

    The MANAGER'S QUEUE is get_pending_validations(manager_codes=visible), and
    it filters on `deal.staff_code in manager_codes`. A deal whose staff_code
    resolves into NOBODY's tree therefore appears in NO queue - while still
    blocking its owner.

    That is an orphan: immovable for the owner, invisible to every manager,
    and nothing in the interface can clear it. This finds them.
    """
    from utils.core import PipelineManager, UserManager
    from utils.api_pipeline_scope import get_staff_roster

    pm = PipelineManager()
    deals = list(getattr(pm, "deals", []) or [])

    # Every staff code any manager can see - the union of all trees.
    seen_by_someone = set()
    roster_codes = set()
    try:
        df = get_staff_roster()
        roster_codes = {str(r.get("Staff Code") or "").strip()
                        for _i, r in df.iterrows()}
        roster_codes.discard("")
        from utils.api_pipeline_scope import get_visible_staff_codes
        users = (UserManager().users or {})
        for _u, rec in users.items():
            try:
                seen_by_someone |= {str(c) for c in get_visible_staff_codes(rec)}
            except Exception:
                continue
    except Exception as exc:
        print("  (could not build the visibility union: %s)" % str(exc)[:60])

    pending = [d for d in deals
               if pm._stage_needs_validation(str(d.get("stage", "")))
               and not d.get("manager_validated")
               and not d.get("cancel_requested")]
    if deal_id:
        pending = [d for d in deals if str(d.get("id")) == deal_id] or pending

    print("  deals: %d | awaiting validation: %d" % (len(deals), len(pending)))

    orphans, ok = [], 0
    for d in pending:
        code = str(d.get("staff_code") or "").strip()
        if not code:
            orphans.append((d, "the deal carries NO staff_code"))
        elif code not in roster_codes and roster_codes:
            orphans.append((d, "owner %s is not in the staff register" % code))
        elif seen_by_someone and code not in seen_by_someone:
            orphans.append((d, "owner %s is in nobody's reporting tree" % code))
        else:
            ok += 1

    print("  in some manager's queue: %d" % ok)
    if not orphans:
        print("  no orphaned validations found.")
        if deal_id and pending:
            d = pending[0]
            print("\n  %s:" % deal_id)
            for k in ("stage", "staff_code", "staff_name", "manager_validated",
                      "cancel_requested", "referral_status", "product_type",
                      "draft"):
                print("     %-20s %r" % (k, d.get(k)))
        return

    print("\n  *** %d deal(s) blocking their owner and visible to NO manager:"
          % len(orphans))
    for d, why in orphans[:12]:
        print("     %-10s %-22s %-16s %s"
              % (str(d.get("id"))[:10], str(d.get("client_name"))[:22],
                 str(d.get("product_type"))[:16], why))
    print("")
    print("  The owner cannot advance or close - the advance path requires")
    print("  manager_validated. No manager can validate, because the queue")
    print("  filters on the owner's staff_code being in their tree.")
    print("")
    print("  FIX THE OWNER'S CODE, not the deal: put the RM in the register")
    print("  under a manager, or correct staff_code on the deal. Setting")
    print("  manager_validated by hand would clear this one and leave the")
    print("  next deal from the same RM stuck in exactly the same way.")


def main():
    deal_id = ""
    if "--deal" in sys.argv:
        i = sys.argv.index("--deal")
        if i + 1 < len(sys.argv):
            deal_id = sys.argv[i + 1].strip()

    rule("1. THE COMMITTEE PALETTE")
    try:
        committees()
    except Exception as exc:
        print("  could not read: %s" % exc)

    rule("2. VALIDATION STATE")
    try:
        stuck_validation(deal_id)
    except Exception as exc:
        print("  could not read: %s" % exc)

    print("\n" + "=" * 78)
    print("Send this output back. Both of these depend on data I cannot see")
    print("from here, and guessing at them has cost time already today.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
