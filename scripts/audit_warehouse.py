#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Audit what is ALREADY on the shelf, and clean it. DRY RUN by default.

DQ1 added the entity-name rule and the duplicate key, but only NEW imports pass
through them. Anything listed before that is still there - which is why the
shelf still shows sentences after the rule was applied. A rule that guards the
door does nothing about what is already inside.

WHAT IT CHECKS
    NOT A NAME      prose lines that carried a postal address into the import
    DUPLICATE       two records that canonicalise to the same business
    NO TOWN         listed, but with nothing to filter on
    NO CONTACT      no phone and no email - claimable, but not actionable

WHAT IT DOES ABOUT IT
    --apply ARCHIVES the bad ones. It does NOT delete them: archived records
    keep their reason and stay searchable, so if the rule turns out to be too
    strict you can see exactly what it took and put them back. Deleting would
    make that impossible.

    Duplicates keep the OLDEST record - it may already have been claimed or
    enriched, and discarding the one with history to keep a fresh empty copy
    would be backwards.

    python scripts\\audit_warehouse.py
    python scripts\\audit_warehouse.py --apply
    python scripts\\audit_warehouse.py --apply --names-only   (skip the softer checks)
"""
import os
import sys

sys.path.insert(0, os.getcwd())


def main():
    apply = "--apply" in sys.argv
    names_only = "--names-only" in sys.argv

    try:
        from utils.deals_warehouse import (all_prospects, canonical_key,
                                           archive, STATUS_AVAILABLE)
    except Exception as exc:
        print("ABORT: %s  (apply patch_dq1_clean_warehouse.py first)" % exc)
        return 1
    try:
        import importlib.util
        spec = importlib.util.spec_from_file_location(
            "_ex", os.path.join("scripts", "extract_register_pdf.py"))
        ex = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(ex)
        looks_like_entity = ex.looks_like_entity
    except Exception as exc:
        print("ABORT: could not load the name rule: %s" % exc)
        return 1

    live = [p for p in all_prospects() if p.get("status") == STATUS_AVAILABLE]
    print("=" * 76)
    print("WAREHOUSE AUDIT")
    print("=" * 76)
    print("  on the shelf   %d available (of %d total)"
          % (len(live), len(all_prospects())))

    not_a_name, dupes, no_town, no_contact = [], [], [], []
    by_key = {}
    for p in sorted(live, key=lambda r: str(r.get("created_at") or "")):
        name = str(p.get("name") or "")
        ok, why = looks_like_entity(name)
        if not ok:
            not_a_name.append((p, why))
            continue
        key = p.get("canonical_key") or canonical_key(name)
        if key in by_key:
            dupes.append((p, by_key[key]))
            continue
        by_key[key] = p
        if not str(p.get("town") or "").strip():
            no_town.append(p)
        if not (str(p.get("contact_phone") or "").strip()
                or str(p.get("contact_email") or "").strip()):
            no_contact.append(p)

    print("\n  NOT A NAME     %d" % len(not_a_name))
    for p, why in not_a_name[:8]:
        print("     %-56s (%s)" % (str(p.get("name"))[:56], why))
    if len(not_a_name) > 8:
        print("     ... and %d more" % (len(not_a_name) - 8))

    print("\n  DUPLICATE      %d" % len(dupes))
    for p, kept in dupes[:6]:
        print("     %-40s == %s" % (str(p.get("name"))[:40], str(kept.get("name"))[:30]))
    if len(dupes) > 6:
        print("     ... and %d more" % (len(dupes) - 6))

    print("\n  NO TOWN        %d   (listed, but nothing to filter on)" % len(no_town))
    print("  NO CONTACT     %d   (claimable, but not actionable)" % len(no_contact))

    clean = len(live) - len(not_a_name) - len(dupes)
    print("\n" + "=" * 76)
    print("  CLEAN          %d of %d" % (clean, len(live)))
    print("=" * 76)
    print("  --apply ARCHIVES the not-a-name and duplicate rows. Archived, not")
    print("  deleted: they keep their reason and stay searchable, so if the")
    print("  rule proves too strict you can see exactly what it took.")
    if not names_only:
        print("  NO TOWN and NO CONTACT are NOT archived - a prospect with a")
        print("  name and nothing else is still a prospect somebody can chase.")

    if not apply:
        print("\nDRY RUN - nothing changed. Re-run with --apply.")
        return 0

    done = failed = 0
    for p, why in not_a_name:
        try:
            archive(p["id"], "audit", "Not a company name: %s" % why)
            done += 1
        except Exception:
            failed += 1
    for p, kept in dupes:
        try:
            archive(p["id"], "audit",
                    "Duplicate of %s (%s)" % (kept.get("name"), kept.get("id")))
            done += 1
        except Exception:
            failed += 1

    print("\narchived %d (%d failed)" % (done, failed))
    print("Restart uvicorn. The shelf should now show only real businesses.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
