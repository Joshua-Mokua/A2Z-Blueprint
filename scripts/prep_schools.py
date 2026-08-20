#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Turn Kenya's school register into warehouse records, with the level and the
ownership on the record rather than buried in a note.

RULING (2026-08-20): "on the subs we can have primary schools, secondary,
universities, tertiary and TVETs, then we can have public and private as well
... there is also a category of church owned."

The Ministry publishes all three, under different names:

    Level_        PRIMARY SCHOOL / SECONDARY SCHOOL / ...   -> subsector
    Status        PUBLIC / PRIVATE                          -> ownership
    SchSponsor    RELIGIOUS ORGANIZATION, CATHOLIC, ACK,    -> church, when the
                  PCEA, SDA, MUSLIM, GOVERNMENT, COMMUNITY     sponsor is one

CHURCH-SPONSORED IS NOT THE SAME AS PRIVATE. A church-sponsored public primary
school is government-funded with a religious sponsor - that is a different
customer from a private academy, and lumping them together would mislead an RM
about who they are calling.

So ownership is one of: public, private, church, community. A school sponsored
by a religious organisation is CHURCH whatever its funding status, because that
is who an officer would go and see.

    python scripts\\prep_schools.py ke_primary_schools.csv
    python scripts\\prep_schools.py ke_primary_schools.csv --keep private,church
    python scripts\\prep_schools.py ke_primary_schools.csv --keep all --min-pupils 200

--min-pupils is a size signal, the way beds were for hospitals. A school with
1,200 pupils collects real fees; one with 40 does not.

Writes a CSV in the shape import_business_register.py reads.
"""
import csv
import os
import sys

CHURCH = ("religious", "catholic", "ack", "anglican", "pcea", "sda",
          "seventh day", "muslim", "islamic", "church", "mission",
          "friends", "methodist", "baptist", "quaker", "kec", "aic",
          "africa inland", "salvation army", "hindu", "sikh")
PRIVATE = ("private", "individual", "proprietor", "company", "trust")
COMMUNITY = ("community", "harambee", "cdf", "self help", "ngo",
             "non-governmental")
PUBLIC = ("government", "gok", "ministry", "county", "local authority",
          "public", "teachers service")

LEVELS = (
    ("primary", "Primary school"),
    ("secondary", "Secondary school"),
    ("tvet", "TVET"), ("technical", "TVET"), ("polytechnic", "TVET"),
    ("vocational", "TVET"),
    ("university", "University"), ("college", "Tertiary college"),
    ("tertiary", "Tertiary college"),
    ("ecd", "Early childhood"), ("nursery", "Early childhood"),
    ("pre-primary", "Early childhood"),
    ("special", "Special needs school"),
)


def _ownership(status, sponsor):
    """Who runs it. The SPONSOR decides before the funding status does.

    A church-sponsored public school is a different customer from a private
    academy, and both are different from a government school. An RM going to
    see the head of a Catholic-sponsored primary is having a conversation with
    the diocese, not with the Ministry.
    """
    sp = str(sponsor or "").lower()
    st = str(status or "").lower()
    if any(w in sp for w in CHURCH):
        return "church"
    if any(w in sp for w in PRIVATE) or "private" in st:
        return "private"
    if any(w in sp for w in COMMUNITY):
        return "community"
    if any(w in sp for w in PUBLIC) or "public" in st:
        return "public"
    return "other"


def _level(raw):
    t = str(raw or "").lower()
    for key, label in LEVELS:
        if key in t:
            return label
    return "School"


def main():
    if len(sys.argv) < 2 or sys.argv[1].startswith("--"):
        print("ABORT: give the CSV, e.g.")
        print("   python scripts\\prep_schools.py ke_primary_schools.csv")
        return 1
    path = sys.argv[1]
    keep, min_pupils = "", 0
    for flag in ("--keep", "--min-pupils"):
        if flag in sys.argv:
            i = sys.argv.index(flag)
            if i + 1 < len(sys.argv):
                if flag == "--keep":
                    keep = sys.argv[i + 1].lower()
                else:
                    try:
                        min_pupils = int(sys.argv[i + 1])
                    except ValueError:
                        min_pupils = 0
    if not os.path.isfile(path):
        print("ABORT: %s not found." % path)
        return 1

    rows = list(csv.DictReader(open(path, encoding="utf-8-sig", errors="ignore")))
    if not rows:
        print("ABORT: the file is empty.")
        return 1

    def col(r, *names):
        for n in names:
            for k in r:
                if k.strip().lower() == n:
                    return str(r[k] or "").strip()
        return ""

    def enrol(r):
        for n in ("totalenrol", "total_enrolment", "enrolment", "enrollment"):
            v = col(r, n)
            if v:
                try:
                    return int(float(v))
                except ValueError:
                    pass
        return 0

    own_tally, lvl_tally = {}, {}
    for r in rows:
        o = _ownership(col(r, "status"), col(r, "schsponsor", "sponsor"))
        own_tally[o] = own_tally.get(o, 0) + 1
        l = _level(col(r, "level_", "level"))
        lvl_tally[l] = lvl_tally.get(l, 0) + 1

    print("=" * 76)
    print("KENYA'S SCHOOLS")
    print("=" * 76)
    print("  schools in the file   %d\n" % len(rows))
    print("  WHO RUNS THEM")
    for o, n in sorted(own_tally.items(), key=lambda x: -x[1]):
        print("     %-12s %6d" % (o, n))
    print("\n  WHAT THEY ARE")
    for l, n in sorted(lvl_tally.items(), key=lambda x: -x[1]):
        print("     %-24s %6d" % (l, n))

    if not keep:
        print("\n  Nothing written. Choose what to import:")
        print("     python scripts\\prep_schools.py %s --keep private,church"
              % os.path.basename(path))
        print("     python scripts\\prep_schools.py %s --keep all --min-pupils 200"
              % os.path.basename(path))
        print("\n  CHURCH IS NOT PRIVATE. A church-sponsored public school is")
        print("  government-funded with a religious sponsor - a different")
        print("  customer from a private academy, and the RM is talking to the")
        print("  diocese rather than the Ministry.")
        return 0

    wanted = ({"public", "private", "church", "community", "other"}
              if keep.strip() == "all"
              else {w.strip() for w in keep.split(",") if w.strip()})
    unknown = wanted - {"public", "private", "church", "community", "other"}
    if unknown:
        print("\nABORT: unknown group(s): %s" % ", ".join(sorted(unknown)))
        return 1

    out_rows, small = [], 0
    for r in rows:
        own = _ownership(col(r, "status"), col(r, "schsponsor", "sponsor"))
        if own not in wanted:
            continue
        pupils = enrol(r)
        if min_pupils and pupils < min_pupils:
            small += 1
            continue
        name = col(r, "name_of_sc", "name_of_school", "name", "school_name")
        if len(name) < 4:
            continue
        level = _level(col(r, "level_", "level"))
        county = (col(r, "county") or col(r, "district")
                  or col(r, "costituenc", "constituency"))
        where = ", ".join(x for x in (col(r, "location"),
                                      col(r, "division"),
                                      col(r, "costituenc", "constituency")) if x)
        out_rows.append({
            "company_name": name.title(),
            "industry_description": "%s - Education" % level,
            # THE TWO THINGS AN OFFICER FILTERS BY, on the record itself rather
            # than in a note nobody can search.
            "subsector": "%s (%s)" % (level, own),
            "town": county,
            "company_phone": "", "company_email": "", "contact_name": "",
            "postal_address": "",
            "physical_location": where,
            "website": "",
            "notes": " ".join(x for x in (
                ("%d pupils" % pupils) if pupils else "",
                ("sponsor: %s" % col(r, "schsponsor", "sponsor"))
                if col(r, "schsponsor", "sponsor") else "",
                col(r, "type1"), col(r, "type2")) if x).strip(),
        })

    if not out_rows:
        print("\nNothing matched. Try a wider --keep or a lower --min-pupils.")
        return 0

    out = "schools_%s.csv" % keep.replace(",", "_")
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
    print("  schools        %d" % len(out_rows))
    if min_pupils:
        print("  dropped        %d under %d pupils" % (small, min_pupils))
    print("\n  TOP AREAS")
    for c, n in sorted(counties.items(), key=lambda x: -x[1])[:8]:
        print("     %-24s %d" % (c[:24], n))
    print("\n  SAMPLE")
    for r in out_rows[:5]:
        print("     %-38s %-26s %s" % (r["company_name"][:38],
                                       r["subsector"][:26], r["notes"][:26]))

    print("\n\nwrote %s" % out)
    print("\n  NO PHONE OR EMAIL - the Ministry does not publish them, and this")
    print("  extract is from 2013, so names will have moved on. Say the year in")
    print("  --source so nobody treats it as current.")
    print("\nIf it looks right:")
    print("   python scripts\\import_business_register.py %s --apply \\" % out)
    print("       --source \"Ministry of Education school register, 2013\" \\")
    print("       --licence \"published register\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
