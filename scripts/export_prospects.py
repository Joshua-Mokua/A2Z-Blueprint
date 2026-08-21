#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Take the shelf out to be enriched, and bring it back. READ ONLY on export.

RULING (2026-08-20): "I need to build a download that can allow me paste the
same to other sites to help me clean with additional information until we get
it to validation threshold."

    python scripts\\export_prospects.py
    python scripts\\export_prospects.py --sector "Financial Services"
    python scripts\\export_prospects.py --subsector SACCO --county Nairobi
    python scripts\\export_prospects.py --missing phone --out saccos_no_phone.csv

WHAT COMES OUT is the shape import_business_register.py reads, plus two columns
it ignores: `_missing` (what this record still needs) and `_complete` (how far
along it is). So the file can be pasted into a search, a directory or a
spreadsheet, filled in, and imported straight back with --update.

THE source_ref COLUMN IS THE POINT. It is how a record found its way in, and
how the update finds it again - even after somebody has corrected the name.
Leave that column alone and edits land on the right record; delete it and they
will not.

SORTED BY WHAT IS MISSING, most incomplete first, because the point of the
exercise is to move records toward the validation threshold, not to admire the
ones already there.
"""
import csv
import os
import sys

sys.path.insert(0, os.getcwd())

COLUMNS = ["source_ref", "company_name", "industry_description", "subsector",
           "town", "company_phone", "company_email", "contact_name",
           "postal_address", "physical_location", "website", "notes",
           # ── FOR A SPREADSHEET AND FOR A MODEL ──────────────────────────
           # RULING (2026-08-20): "the ability to download with the fields
           # with % calculator so that I can upload to other models to add to
           # the data."
           #
           # _complete reads "2 of 6", which a person understands and a
           # spreadsheet cannot sort. _percent is the same thing as a NUMBER,
           # so the file can be sorted, filtered and charted.
           #
           # _needs is the row written as an instruction. A model handed
           # "Find the phone, email and website for Tenwek Mission Hospital,
           # Bomet" can act on it; handed a column called _missing it has to
           # infer what is wanted.
           "_complete", "_percent", "_missing", "_needs"]

WANTED = [("company_phone", "phone"), ("company_email", "email"),
          ("contact_name", "contact"), ("town", "town"),
          ("physical_location", "location"), ("website", "website")]


def main():
    out = ""
    sector = subsector = county = status = missing = ""
    # ── HANDING 41,878 ROWS TO ANYBODY IS NOT A REQUEST, IT IS A DUMP ───────
    # RULING (2026-08-21): "I need that link to download and hand to an agent
    # to do a deep search."
    #
    # One file of forty thousand rows is unworkable for a person and beyond
    # most models' context. --chunk splits it into numbered files that can be
    # handed out separately, worked on in parallel, and brought back one at a
    # time - so a mistake in one costs one batch rather than the lot.
    chunk = 0
    if "--chunk" in sys.argv:
        i = sys.argv.index("--chunk")
        if i + 1 < len(sys.argv):
            try:
                chunk = max(0, int(sys.argv[i + 1]))
            except ValueError:
                chunk = 0
    for flag, name in (("--out", "out"), ("--sector", "sector"),
                       ("--subsector", "subsector"), ("--county", "county"),
                       ("--status", "status"), ("--missing", "missing")):
        if flag in sys.argv:
            i = sys.argv.index(flag)
            if i + 1 < len(sys.argv):
                v = sys.argv[i + 1]
                if name == "out":
                    out = v
                elif name == "sector":
                    sector = v.lower()
                elif name == "subsector":
                    subsector = v.lower()
                elif name == "county":
                    county = v.lower()
                elif name == "status":
                    status = v.lower()
                else:
                    missing = v.lower()

    import utils.deals_warehouse as W
    rows = []
    for p in (W.all_prospects() or []):
        if sector and sector not in str(p.get("sector", "")).lower():
            continue
        if subsector and subsector not in str(p.get("subsector", "")).lower():
            continue
        if county and county not in str(p.get("town", "")).lower():
            continue
        if status and status != str(p.get("status", "")).lower():
            continue

        gaps = [label for field, label in WANTED
                if not str(p.get(_map(field), "") or "").strip()]
        if missing and missing not in [g.lower() for g in gaps]:
            continue
        have = len(WANTED) - len(gaps)
        rows.append({
            "source_ref": p.get("source_ref", ""),
            "company_name": p.get("name", ""),
            "industry_description": p.get("sector", ""),
            "subsector": p.get("subsector", ""),
            "town": p.get("town", ""),
            "company_phone": p.get("contact_phone", ""),
            "company_email": p.get("contact_email", ""),
            "contact_name": p.get("contact_name", ""),
            "postal_address": p.get("postal_address", ""),
            "physical_location": p.get("physical_location", ""),
            "website": p.get("website", ""),
            "notes": p.get("notes", ""),
            "_complete": "%d of %d" % (have, len(WANTED)),
            "_percent": int(round(100.0 * have / len(WANTED))),
            "_missing": ", ".join(gaps),
            "_needs": ("" if not gaps else
                       "Find the %s for %s%s." % (
                           ", ".join(gaps[:-1]) + " and " + gaps[-1]
                           if len(gaps) > 1 else gaps[0],
                           p.get("name", ""),
                           (", " + str(p.get("town"))) if p.get("town") else "")),
        })

    if not rows:
        print("Nothing matches. Try fewer filters, or --status under_validation.")
        return 0

    # Most incomplete first - the point is to move records forward, not to
    # look at the ones already done.
    rows.sort(key=lambda r: (-len(r["_missing"].split(", ")) if r["_missing"] else 0,
                             r["company_name"]))

    if not out:
        bits = [b for b in (subsector or sector, county, status) if b]
        out = "prospects_%s.csv" % ("_".join(bits).replace(" ", "_") or "all")

    written = []
    if chunk and len(rows) > chunk:
        stem = out[:-4] if out.lower().endswith(".csv") else out
        for n in range(0, len(rows), chunk):
            part = "%s_%02d.csv" % (stem, n // chunk + 1)
            with open(part, "w", encoding="utf-8-sig", newline="") as fh:
                w = csv.DictWriter(fh, fieldnames=COLUMNS)
                w.writeheader()
                for r in rows[n:n + chunk]:
                    w.writerow(r)
            written.append((part, len(rows[n:n + chunk])))
    else:
        with open(out, "w", encoding="utf-8-sig", newline="") as fh:
            w = csv.DictWriter(fh, fieldnames=COLUMNS)
            w.writeheader()
            for r in rows:
                w.writerow(r)
        written.append((out, len(rows)))

    gapcount = {}
    for r in rows:
        for g in (r["_missing"].split(", ") if r["_missing"] else []):
            gapcount[g] = gapcount.get(g, 0) + 1

    print("=" * 72)
    print("EXPORTED FOR ENRICHMENT")
    print("=" * 72)
    if len(written) > 1:
        print("  files       %d" % len(written))
        for f, n in written[:6]:
            print("     %-44s %d rows" % (os.path.basename(f), n))
        if len(written) > 6:
            print("     ... and %d more" % (len(written) - 6))
    else:
        print("  file        %s" % written[0][0])
    print("  prospects   %d" % len(rows))
    full = sum(1 for r in rows if not r["_missing"])
    avg = sum(r["_percent"] for r in rows) / float(len(rows))
    print("  complete    %d have everything (%.0f%%)" % (full, 100.0 * full / len(rows)))
    print("  average     %.0f%% complete across the file" % avg)
    if gapcount:
        print("\n  WHAT IS MISSING, most common first:")
        for g, n in sorted(gapcount.items(), key=lambda x: -x[1]):
            print("     %-14s %d record(s)" % (g, n))
        top = sorted(gapcount.items(), key=lambda x: -x[1])[0]
        print("\n  Filling %r alone moves %d records forward - more than any"
              % (top[0], top[1]))
        print("  other single field.")

    print("\n  Fill the blanks in %s, then bring it back:" % out)
    print("     python scripts\\import_business_register.py %s --update --apply \\" % out)
    print("         --source \"<the same --source you imported with>\"")
    print("\n  LEAVE THE source_ref COLUMN ALONE. It is how an edit finds its")
    print("  way back to the right record, even after a name is corrected.")
    return 0


def _map(field):
    return {"company_phone": "contact_phone", "company_email": "contact_email",
            "contact_name": "contact_name", "town": "town",
            "physical_location": "physical_location",
            "website": "website"}.get(field, field)


if __name__ == "__main__":
    sys.exit(main())
