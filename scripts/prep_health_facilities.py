#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Turn the Master Health Facility List into prospects a bank can actually serve.

The Ministry of Health publishes 12,394 facilities. MOST OF THEM ARE NOT
PROSPECTS: a government dispensary in Matungu banks with the Treasury, not with
Ecobank. Importing all of them would bury 800 real businesses under 11,000
public clinics and make the warehouse worthless to an RM.

So this reports the ownership breakdown FIRST and imports only what you choose.

    python scripts\\prep_health_facilities.py ke_hospitals.csv
    python scripts\\prep_health_facilities.py ke_hospitals.csv --keep private
    python scripts\\prep_health_facilities.py ke_hospitals.csv --keep private,faith --min-beds 10

WHAT IT KEEPS BY DEFAULT: nothing. It shows you the breakdown and stops,
because "which of these does the bank want" is a commercial judgement and not
mine to make quietly.

    private   private practice, private companies, private institutions
    faith     faith-based, mission, church-run - most run real balance sheets
    ngo       non-governmental, community
    public    ministry of health, county government - included only if asked

BEDS ARE A SIZE SIGNAL. --min-beds 10 drops the one-room clinics and leaves
facilities with something to finance. A hospital with 60 beds is a different
conversation from a dispensary with none.

The county becomes the town, the facility type becomes the subsector, and the
whole thing lands in the shape import_business_register.py reads.
"""
import csv
import os
import sys

GROUPS = {
    "private": ("private practice", "private company", "private institution",
                "private", "co-operative", "cooperative", "company"),
    "faith":   ("faith", "mission", "church", "christian", "muslim", "kec",
                "cha", "supkem", "seventh day"),
    "ngo":     ("non-governmental", "ngo", "community", "charit", "trust"),
    "public":  ("ministry of health", "county government", "public",
                "prisons", "police", "military", "university", "parastatal"),
}


def _group(owner_type, owner):
    blob = ("%s %s" % (owner_type or "", owner or "")).lower()
    # Public first: "Ministry of Health" must not fall into "private" because
    # the word "institution" appears somewhere in the owner name.
    for name in ("public", "faith", "ngo", "private"):
        if any(w in blob for w in GROUPS[name]):
            return name
    return "other"


def main():
    if len(sys.argv) < 2 or sys.argv[1].startswith("--"):
        print("ABORT: give the CSV, e.g.")
        print("   python scripts\\prep_health_facilities.py ke_hospitals.csv")
        return 1
    path = sys.argv[1]
    keep, min_beds = "", 0
    for flag in ("--keep", "--min-beds"):
        if flag in sys.argv:
            i = sys.argv.index(flag)
            if i + 1 < len(sys.argv):
                if flag == "--keep":
                    keep = sys.argv[i + 1].lower()
                else:
                    try:
                        min_beds = int(sys.argv[i + 1])
                    except ValueError:
                        min_beds = 0
    if not os.path.isfile(path):
        print("ABORT: %s not found." % path)
        return 1

    rows = list(csv.DictReader(open(path, encoding="utf-8-sig")))
    if not rows:
        print("ABORT: the file is empty.")
        return 1

    def col(r, *names):
        for n in names:
            for k in r:
                if k.strip().lower() == n:
                    return str(r[k] or "").strip()
        return ""

    tally, by_type = {}, {}
    for r in rows:
        g = _group(col(r, "owner type"), col(r, "owner"))
        tally[g] = tally.get(g, 0) + 1
        if g != "public":
            t = col(r, "facility type") or "(none)"
            by_type[t] = by_type.get(t, 0) + 1

    print("=" * 76)
    print("WHO OWNS KENYA'S HEALTH FACILITIES")
    print("=" * 76)
    print("  facilities in the file   %d\n" % len(rows))
    for g in ("private", "faith", "ngo", "public", "other"):
        n = tally.get(g, 0)
        if n:
            print("     %-10s %6d   %s" % (g, n, "<- a bank can serve these"
                                           if g in ("private", "faith", "ngo") else ""))

    if not keep:
        print("\n  NOT-PUBLIC FACILITIES BY TYPE")
        for t, n in sorted(by_type.items(), key=lambda x: -x[1])[:12]:
            print("     %-40s %d" % (t[:40], n))
        print("\n  Nothing has been written. Choose what the bank wants:")
        print("     python scripts\\prep_health_facilities.py %s --keep private"
              % os.path.basename(path))
        print("     python scripts\\prep_health_facilities.py %s --keep private,faith --min-beds 10"
              % os.path.basename(path))
        print("\n  --min-beds drops the one-room clinics. A hospital with 60")
        print("  beds is a different conversation from a dispensary with none.")
        return 0

    wanted = {w.strip() for w in keep.split(",") if w.strip()}
    unknown = wanted - set(GROUPS)
    if unknown:
        print("\nABORT: unknown group(s): %s" % ", ".join(sorted(unknown)))
        print("       Known: %s" % ", ".join(sorted(GROUPS)))
        return 1

    out_rows, dropped_beds, closed = [], 0, 0
    for r in rows:
        if _group(col(r, "owner type"), col(r, "owner")) not in wanted:
            continue
        if col(r, "closed").lower() == "yes" or \
           col(r, "operation status").lower() not in ("", "operational"):
            closed += 1
            continue
        beds = col(r, "beds and cots") or col(r, "beds") or "0"
        try:
            b = int(float(beds))
        except ValueError:
            b = 0
        if min_beds and b < min_beds:
            dropped_beds += 1
            continue
        name = col(r, "officialname") or col(r, "name")
        if len(name) < 4:
            continue
        ftype = col(r, "facility type")
        ward = col(r, "ward")
        sub = col(r, "sub county")
        out_rows.append({
            "company_name": name,
            "industry_description": "%s - Healthcare" % (ftype or "Health facility"),
            "town": col(r, "county"),
            "company_phone": "",
            "company_email": "",
            "contact_name": "",
            "postal_address": "",
            "physical_location": ", ".join(x for x in (ward, sub) if x),
            "website": "",
            "notes": " ".join(x for x in (
                ("%s beds" % b) if b else "",
                ("owner: %s" % col(r, "owner")) if col(r, "owner") else "",
                ("reg. %s" % col(r, "registration_number"))
                if col(r, "registration_number") else "") if x).strip(),
        })

    if not out_rows:
        print("\nNothing matched. Try a wider --keep or a lower --min-beds.")
        return 0

    out = "health_facilities_%s.csv" % keep.replace(",", "_")
    with open(out, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        for r in out_rows:
            w.writerow(r)

    counties = {}
    for r in out_rows:
        counties[r["town"] or "(none)"] = counties.get(r["town"] or "(none)", 0) + 1

    print("\n" + "-" * 76)
    print("KEPT: %s" % ", ".join(sorted(wanted)))
    print("-" * 76)
    print("  facilities     %d" % len(out_rows))
    if min_beds:
        print("  dropped        %d below %d beds" % (dropped_beds, min_beds))
    if closed:
        print("  not operational %d skipped" % closed)
    print("\n  TOP COUNTIES")
    for c, n in sorted(counties.items(), key=lambda x: -x[1])[:8]:
        print("     %-22s %d" % (c, n))
    print("\n  SAMPLE")
    for r in out_rows[:4]:
        print("     %-44s %-12s %s" % (r["company_name"][:44], r["town"],
                                       r["notes"][:30]))

    print("\n\nwrote %s" % out)
    print("\n  NO PHONE OR EMAIL - the Ministry does not publish them. These")
    print("  land as names with a county and a size, and the export round")
    print("  trip is how they get contacts:")
    print("     python scripts\\export_prospects.py --missing phone")
    print("\nIf it looks right:")
    print("   python scripts\\import_business_register.py %s --apply \\" % out)
    print("       --source \"Kenya Master Health Facility List\" \\")
    print("       --licence \"published register\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
