#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Read a register published as an HTML table - TVETA and its like.

Built from what diag_html_table.py actually found:

    S/N | Name | Reg. No | Category | Type | County | Expiry Date | Status | Action
    1   | MARENGONI COMMUNITY TECHNICAL | TVETA/PRIVATE/TVC/0028/2019 | VTC |
          Private | Kajiado | 2029-10-09 | Registered and Licensed | Details

Three lists on one page: 2,107 accredited, 1,071 registered, 23 others. They
OVERLAP - the same college appears on more than one - and that is correct, not
a fault. The name-and-place key means the second sighting is skipped rather
than duplicated.

    python scripts\\extract_html_register.py tveta_list.html --label TVET
    python scripts\\extract_html_register.py tveta_list.html --label TVET --table 2

COLUMNS ARE MATCHED BY HEADER, not by position, because the three tables on
this page do not have identical widths and a register published next year will
not either.

AN EXPIRED LICENCE IS NOT A PROSPECT. A row whose status says revoked,
suspended or expired is counted and skipped - a bank calling a college whose
licence was pulled is worse than not calling.
"""
import csv
import os
import re
import sys

TAG = re.compile(r"<[^>]+>")
CELL = re.compile(r"<t[dh][^>]*>(.*?)</t[dh]>", re.I | re.S)
ROW = re.compile(r"<tr[^>]*>(.*?)</tr>", re.I | re.S)
TABLE = re.compile(r"<table[^>]*>(.*?)</table>", re.I | re.S)

HINTS = {
    "name": ("name", "institution", "institution name", "college"),
    "reg_no": ("reg. no", "reg no", "registration", "licence no", "license no"),
    "category": ("category", "level", "class"),
    "type": ("type", "ownership", "sponsor"),
    "county": ("county", "location", "region", "town"),
    "status": ("status",),
    "expiry": ("expiry date", "expiry", "valid until"),
    "phone": ("phone", "telephone", "mobile", "contact"),
    "email": ("email", "e-mail"),
}

DEAD = ("revoked", "suspended", "expired", "cancelled", "deregistered",
        "closed", "withdrawn")


def _text(html):
    t = TAG.sub(" ", html or "")
    for a, b in (("&nbsp;", " "), ("&amp;", "&"), ("&#039;", "'"),
                 ("&quot;", '"'), ("&lt;", "<"), ("&gt;", ">")):
        t = t.replace(a, b)
    return re.sub(r"\s+", " ", t).strip()


def _town_case(name):
    """Nairobi, not NAIROBI - and not Nairobi West as a county either."""
    t = re.sub(r"\s+", " ", str(name or "")).strip()
    if not t:
        return ""
    if t.isupper() or t.islower():
        t = t.title()
    # A register sometimes gives a ward where a county belongs. Left alone -
    # dropping it would lose the only location the row has.
    return t


def _pick(headers):
    low = [h.strip().lower() for h in headers]
    cols = {}
    for key, hints in HINTS.items():
        for hint in hints:
            if hint in low:
                cols[key] = low.index(hint)
                break
        if key in cols:
            continue
        for i, h in enumerate(low):
            if any(hint in h for hint in hints):
                cols[key] = i
                break
    return cols


def main():
    if len(sys.argv) < 2 or sys.argv[1].startswith("--"):
        print("ABORT: give the saved HTML file, e.g.")
        print("   python scripts\\extract_html_register.py tveta_list.html \\")
        print("       --label TVET")
        return 1
    path = sys.argv[1]
    label = sector = ""
    only = 0
    for flag in ("--label", "--sector", "--table"):
        if flag in sys.argv:
            i = sys.argv.index(flag)
            if i + 1 < len(sys.argv):
                if flag == "--label":
                    label = sys.argv[i + 1]
                elif flag == "--sector":
                    sector = sys.argv[i + 1]
                else:
                    try:
                        only = int(sys.argv[i + 1])
                    except ValueError:
                        only = 0
    sector = sector or "Education"
    if not os.path.isfile(path):
        print("ABORT: %s not found." % path)
        return 1

    html = open(path, encoding="utf-8", errors="ignore").read()
    tables = TABLE.findall(html)
    if not tables:
        print("ABORT: no <table> in this file. Run the diagnostic:")
        print("   python scripts\\diag_html_table.py %s" % os.path.basename(path))
        return 1

    out_rows, dead, blank, seen_tables = [], 0, 0, 0
    for n, t in enumerate(tables, start=1):
        if only and n != only:
            continue
        rows = ROW.findall(t)
        if len(rows) < 3:
            continue
        header = [_text(c) for c in CELL.findall(rows[0])]
        cols = _pick(header)
        if "name" not in cols:
            continue
        seen_tables += 1
        for r in rows[1:]:
            cells = [_text(c) for c in CELL.findall(r)]
            if len(cells) <= cols["name"]:
                continue

            def get(key):
                i = cols.get(key, -1)
                return cells[i] if 0 <= i < len(cells) else ""

            name = get("name")
            if len(name) < 4:
                blank += 1
                continue
            status = get("status")
            if any(w in status.lower() for w in DEAD):
                dead += 1
                continue

            own = get("type").strip().lower()
            ownership = ("private" if "priv" in own
                         else "public" if "pub" in own
                         else own or "")
            category = get("category").strip()
            sub = " ".join(x for x in (label or category, ) if x)
            if ownership:
                sub = "%s (%s)" % (sub, ownership)

            out_rows.append({
                "company_name": name.title() if name.isupper() else name,
                "industry_description": "%s - %s" % (label or category, sector),
                "subsector": sub,
                # TOWN CASING. EPRA writes "Nairobi" on one row and
                # "NAIROBI" on the next, and the shelf then shows them as two
                # towns - 36 in one and 7 in the other, and a filter on either
                # misses the rest. Title case them so they land together.
                "town": _town_case(get("county")),
                "company_phone": get("phone"),
                "company_email": get("email"),
                "contact_name": "",
                "postal_address": "",
                "physical_location": "",
                "website": "",
                "notes": " ".join(x for x in (
                    ("cat. %s" % category) if category else "",
                    ("reg. %s" % get("reg_no")) if get("reg_no") else "",
                    status,
                    ("expires %s" % get("expiry")) if get("expiry") else "",
                ) if x).strip(),
            })

    if not out_rows:
        print("ABORT: no rows came out. Run the diagnostic and send it.")
        return 1

    out = os.path.splitext(os.path.basename(path))[0] + ".csv"
    with open(out, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(out_rows[0].keys()))
        w.writeheader()
        for r in out_rows:
            w.writerow(r)

    subs, counties = {}, {}
    for r in out_rows:
        subs[r["subsector"]] = subs.get(r["subsector"], 0) + 1
        counties[r["town"] or "(none)"] = counties.get(r["town"] or "(none)", 0) + 1

    print("=" * 76)
    print("HTML REGISTER EXTRACT")
    print("=" * 76)
    print("  file        %s" % os.path.basename(path))
    print("  tables read %d" % seen_tables)
    print("  EXTRACTED   %d" % len(out_rows))
    if dead:
        print("  skipped     %d whose licence is revoked, suspended or expired"
              % dead)
        print("              - a bank calling those is worse than not calling")
    if blank:
        print("  blank       %d" % blank)

    print("\n  WHAT THEY ARE")
    for k, n in sorted(subs.items(), key=lambda x: -x[1])[:10]:
        print("     %-34s %d" % (k[:34], n))
    print("\n  TOP COUNTIES")
    for c, n in sorted(counties.items(), key=lambda x: -x[1])[:8]:
        print("     %-22s %d" % (c[:22], n))

    print("\n  SAMPLE")
    for r in out_rows[:5]:
        print("     %-40s %-24s %s" % (r["company_name"][:40],
                                       r["subsector"][:24], r["town"]))

    print("\n\nwrote %s" % out)
    print("\n  THE THREE LISTS ON THIS PAGE OVERLAP - the same college appears")
    print("  on more than one. The import keys on name AND place, so the")
    print("  second sighting is skipped rather than duplicated. Expect a")
    print("  large 'already on the shelf' count, and that is correct.")
    print("\nIf the sample looks right:")
    print("   python scripts\\import_business_register.py %s --apply \\" % out)
    print("       --source \"TVETA register of accredited institutions\" \\")
    print("       --licence \"published register\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
