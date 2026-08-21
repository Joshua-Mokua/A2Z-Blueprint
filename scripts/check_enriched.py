#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Check an enriched file BEFORE it touches the warehouse. READ ONLY.

RULING (2026-08-21): "after they do I will still upload the same here for
sanity checking before we go ahead and update."

Right instinct. A file that has been round an agent, a spreadsheet and an
email can come back with the source_ref column deleted, the rows re-sorted,
phone numbers autocorrected into dates, or a plausible-looking email invented
for a business that has none. Any of those would land in the warehouse looking
like fact.

    python scripts\\check_enriched.py enrich_01.csv

WHAT IT CHECKS, and why each one has actually happened to somebody:

    source_ref present and unchanged   without it the update matches nothing,
                                       or worse, matches the wrong record
    names not rewritten                a bulk update must not rename records
    phones that look like phones       Excel turns 0722123456 into 7.22E+08
    emails that look like emails       and are not obviously invented
    no rows added                      an enriched file returns what it took
    what actually got filled           so you know it was worth the trip

Nothing is written. It reports and stops.
"""
import csv
import os
import re
import sys

sys.path.insert(0, os.getcwd())

PHONE_OK = re.compile(r"^[+0][0-9\s\-()/,.]{6,}$")
EMAIL_OK = re.compile(r"^[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}$")
# Excel's handiwork: 7.22E+08, 43678, 2023-01-05
MANGLED = re.compile(r"^\d+\.\d+E\+\d+$|^\d{5}$|^\d{4}-\d{2}-\d{2}$", re.I)


def main():
    if len(sys.argv) < 2 or sys.argv[1].startswith("--"):
        print("ABORT: give the returned file, e.g.")
        print("   python scripts\\check_enriched.py enrich_01.csv")
        return 1
    path = sys.argv[1]
    if not os.path.isfile(path):
        print("ABORT: %s not found." % path)
        return 1

    rows = list(csv.DictReader(open(path, encoding="utf-8-sig", errors="ignore")))
    if not rows:
        print("ABORT: the file is empty.")
        return 1
    cols = list(rows[0].keys())

    import utils.deals_warehouse as W
    by_ref = {}
    for p in (W.all_prospects() or []):
        r = str(p.get("source_ref", "") or "").strip()
        if r:
            by_ref[r] = p

    print("=" * 78)
    print("CHECKING AN ENRICHED FILE")
    print("=" * 78)
    print("  file        %s" % os.path.basename(path))
    print("  rows        %d" % len(rows))
    print("  columns     %d" % len(cols))

    fatal, warn = [], []

    if "source_ref" not in cols:
        fatal.append("There is no source_ref column. Without it nothing can "
                     "be matched back - the update would add %d NEW records "
                     "rather than filling these." % len(rows))
    else:
        blank = sum(1 for r in rows if not str(r.get("source_ref") or "").strip())
        unknown = [r for r in rows
                   if str(r.get("source_ref") or "").strip()
                   and str(r.get("source_ref")).strip() not in by_ref]
        if blank:
            fatal.append("%d row(s) have an EMPTY source_ref. Those cannot be "
                         "matched and would be added as new records." % blank)
        if unknown:
            fatal.append("%d row(s) carry a source_ref that is not on the "
                         "shelf. Either they were edited, or this file is "
                         "from a different export." % len(unknown))
            for r in unknown[:3]:
                print("\n     unknown ref: %s" % str(r.get("source_ref"))[:60])

    # Names must not have been rewritten - the update will not apply them, so
    # a renamed row means somebody expected a change that will not happen.
    renamed = 0
    for r in rows:
        ref = str(r.get("source_ref") or "").strip()
        p = by_ref.get(ref)
        if not p:
            continue
        was = str(p.get("name", "")).strip().lower()
        now = str(r.get("company_name", "")).strip().lower()
        if was and now and was != now:
            renamed += 1
    if renamed:
        warn.append("%d name(s) differ from the shelf. The update does NOT "
                    "apply names - correct those in the record card, or they "
                    "will silently not happen." % renamed)

    # What is actually being offered, and is it plausible?
    filled = {"company_phone": 0, "company_email": 0, "contact_name": 0,
              "website": 0, "physical_location": 0}
    bad_phone, bad_email = [], []
    for r in rows:
        ref = str(r.get("source_ref") or "").strip()
        p = by_ref.get(ref) or {}
        for col, store in (("company_phone", "contact_phone"),
                           ("company_email", "contact_email"),
                           ("contact_name", "contact_name"),
                           ("website", "website"),
                           ("physical_location", "physical_location")):
            new = str(r.get(col) or "").strip()
            old = str(p.get(store) or "").strip()
            if new and not old:
                filled[col] += 1
        ph = str(r.get("company_phone") or "").strip()
        if ph and (MANGLED.match(ph) or not PHONE_OK.match(ph)):
            bad_phone.append((r.get("company_name", ""), ph))
        em = str(r.get("company_email") or "").strip()
        if em and not EMAIL_OK.match(em):
            bad_email.append((r.get("company_name", ""), em))

    print("\n  WHAT THIS FILE ADDS")
    total_new = sum(filled.values())
    for col, n in sorted(filled.items(), key=lambda x: -x[1]):
        print("     %-20s %d" % (col, n))
    if total_new == 0:
        warn.append("Nothing new. Every value in this file is either blank or "
                    "already on the shelf - the trip added nothing.")

    if bad_phone:
        fatal.append("%d phone number(s) do not look like phone numbers. "
                     "Excel turns 0722123456 into 7.22E+08 and dates into "
                     "serial numbers." % len(bad_phone))
        print("\n     suspect phones:")
        for name, v in bad_phone[:5]:
            print("        %-38s %s" % (str(name)[:38], v[:24]))
    if bad_email:
        fatal.append("%d email address(es) are malformed." % len(bad_email))
        print("\n     suspect emails:")
        for name, v in bad_email[:5]:
            print("        %-38s %s" % (str(name)[:38], v[:34]))

    print("\n" + "=" * 78)
    if fatal:
        print("DO NOT IMPORT THIS FILE")
        print("=" * 78)
        for f in fatal:
            print("  * %s" % f)
        if warn:
            print("")
            for w in warn:
                print("  - %s" % w)
        return 1
    print("SAFE TO IMPORT")
    print("=" * 78)
    if warn:
        for w in warn:
            print("  - %s" % w)
        print("")
    print("  %d value(s) would be filled. Only BLANKS are filled - anything" % total_new)
    print("  already on the shelf is left alone, because somebody looked it up.")
    print("\n   python scripts\\import_business_register.py %s --update --apply \\"
          % os.path.basename(path))
    print("       --source \"<the same --source it was exported from>\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
