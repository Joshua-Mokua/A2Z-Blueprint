#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Remove every prospect from one import, in ONE write. DRY RUN by default.

`delete()` reads and writes the whole store per record - fine for one prospect
removed by hand, hopeless for 435 left behind by an interrupted import. That is
the same quadratic fault that made the import fail in the first place.

    python scripts\\delete_by_source.py --source "Kenya Master Health Facility"
    python scripts\\delete_by_source.py --source "Kenya Master Health Facility" --apply
    python scripts\\delete_by_source.py --run "MFL test 2026-08-20 12:04" --apply

MATCHES ON source_event OR import_run, as a substring, so a partial import can
be named by the register it came from or the exact run that brought it.

IT WILL NOT REMOVE A CLAIMED PROSPECT. If somebody has picked it up, deleting
it under them destroys their work - those are reported and left, and can be
removed one at a time if that is really intended.
"""
import os
import sys

sys.path.insert(0, os.getcwd())


def main():
    apply = "--apply" in sys.argv
    source = run = ""
    for flag in ("--source", "--run"):
        if flag in sys.argv:
            i = sys.argv.index(flag)
            if i + 1 < len(sys.argv):
                if flag == "--source":
                    source = sys.argv[i + 1].strip().lower()
                else:
                    run = sys.argv[i + 1].strip().lower()
    if not (source or run):
        print("ABORT: --source or --run is required.")
        print('   python scripts\\delete_by_source.py --source "Kenya Master Health"')
        return 1

    import utils.deals_warehouse as W
    data = W._read() or {}

    hit, claimed = [], []
    for pid, rec in data.items():
        ev = str(rec.get("source_event", "") or "").lower()
        rn = str(rec.get("import_run", "") or "").lower()
        if (source and source in ev) or (run and run in rn):
            if str(rec.get("claimed_by_code", "") or "").strip():
                claimed.append((pid, rec))
            else:
                hit.append((pid, rec))

    print("=" * 72)
    print("REMOVE AN IMPORT")
    print("=" * 72)
    print("  on the shelf       %d" % len(data))
    print("  matched            %d" % (len(hit) + len(claimed)))
    print("  TO REMOVE          %d" % len(hit))
    if claimed:
        print("  claimed, LEFT      %d" % len(claimed))
        print("\n  Somebody has picked these up. Removing them would destroy")
        print("  their work, so they stay:")
        for pid, rec in claimed[:5]:
            print("     %-34s claimed by %s" % (str(rec.get("name"))[:34],
                                                rec.get("claimed_by_name") or "?"))
    if not hit:
        print("\n  Nothing to remove.")
        return 0
    print("\n  SAMPLE OF WHAT GOES")
    for pid, rec in hit[:5]:
        print("     %-40s %s" % (str(rec.get("name"))[:40],
                                 str(rec.get("source_event"))[:28]))
    if len(hit) > 5:
        print("     ... and %d more" % (len(hit) - 5))
    print("\n  after this the shelf holds %d" % (len(data) - len(hit)))

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for pid, _rec in hit:
        data.pop(pid, None)
    W._write(data)
    print("\nremoved %d in one write." % len(hit))
    print("\n   python scripts\\verify_warehouse_store.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
