#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Read a RULED-TABLE register - CBK's forex bureaus and money remittance.

Built from what diag_register_pdf.py actually found in the document, not from
an imitation of it. The page reports 364 horizontal and 364 vertical lines and
pdfplumber returns real cells:

    ['8', 'Carrington Forex\\nBureau Limited', 'Maa Properties,\\nJabavu Road,
      Hurlingham, Nairobi', 'P.O Box 61029-00200, NAIROBI.\\nTel: 0762300370\\n
      Carringtoneforex@gmail.com', 'November 12,\\n2024']

So the columns are already cut correctly and there is nothing to guess at. The
work is in ONE cell: "Contact Details" glues a postal box, a town, a telephone,
an email and often a fax into a single lump, and those have to come apart.

    python scripts\\extract_register_table.py cbk_forex.pdf --label "Forex bureau"
    python scripts\\extract_register_table.py cbk_mrp.pdf --label "Money remittance"

WHAT IT WILL NOT DO: invent. A row whose name cell is empty, or which is the
repeated header, is reported and skipped rather than becoming a bureau.

Writes a CSV in the shape import_business_register.py reads.
"""
import csv
import os
import re
import sys

HEADERS = ("name of bureau", "name of", "location", "contact details",
           "date of", "licencing", "central bank of kenya", "directory of",
           "name of the", "no.")

EMAIL = re.compile(r"[A-Za-z0-9._%+\-]+@[A-Za-z0-9.\-]+\.[A-Za-z]{2,}")
# "Tel: 0762300370" / "Tel. 020 - 445995, 0722 - 703121" / "Cell: 0721-411300"
# THE DASH IS NOT A HYPHEN. CBK writes "Tel. 020 – 445995" with an EN DASH,
# and a character class of plain hyphens matched nothing at all - every phone
# on those rows would have been dropped in silence.
PHONE = re.compile(r"(?:tel|cell|mobile|phone)[.:]?\s*"
                   r"([0-9+][0-9\s\-\u2010-\u2015/,()]{5,})", re.I)
FAX = re.compile(r"fax[^\n]*", re.I)
# The box number ends where the next thing begins. Anchoring on the line end
# swallowed the telephone, the email and the street - the whole cell arrived as
# a "postal address".
POSTAL = re.compile(r"(P\.?\s*O\.?\s*Box.*?)(?=\s*(?:Tel|Cell|Fax|Mobile|Phone)\b"
                    r"|\s*[A-Za-z0-9._%+\-]+@|$)", re.I | re.S)

COUNTIES = ["Nairobi", "Mombasa", "Kisumu", "Nakuru", "Eldoret", "Uasin Gishu",
            "Kiambu", "Machakos", "Kajiado", "Nyeri", "Meru", "Kakamega",
            "Bungoma", "Kilifi", "Kericho", "Kitale", "Malindi", "Thika",
            "Naivasha", "Garissa", "Wajir", "Mandera", "Isiolo", "Nanyuki",
            "Embu", "Migori", "Busia", "Narok", "Lamu", "Diani", "Watamu"]


def _flat(cell):
    return re.sub(r"\s+", " ", str(cell or "").replace("\n", " ")).strip()


def _town(location, contact=""):
    """Where the business IS - not where its post goes.

    A Mombasa bureau with a Nairobi postal box was landing in Nairobi, because
    both towns appeared in one blob and Nairobi came first in the list. An RM
    sent to the wrong town is a wasted morning, so the STREET ADDRESS decides
    and the postal box is only a fallback.
    """
    for source in (location, contact):
        blob = str(source or "")
        if not blob:
            continue
        hits = [(m.start(), c) for c in COUNTIES
                for m in [re.search(r"\b%s\b" % re.escape(c), blob, re.I)] if m]
        if hits:
            # The last town named in a street address is the town: "Moi
            # Avenue, Mombasa" ends where the place is.
            c = sorted(hits)[-1][1]
            return "Uasin Gishu" if c.lower() == "eldoret" else c
    return ""


def main():
    if len(sys.argv) < 2 or sys.argv[1].startswith("--"):
        print("ABORT: give the file, e.g.")
        print("   python scripts\\extract_register_table.py cbk_forex.pdf \\")
        print("       --label \"Forex bureau\"")
        return 1
    path = sys.argv[1]
    label = sector = ""
    for flag in ("--label", "--sector"):
        if flag in sys.argv:
            i = sys.argv.index(flag)
            if i + 1 < len(sys.argv):
                if flag == "--label":
                    label = sys.argv[i + 1]
                else:
                    sector = sys.argv[i + 1]
    sector = sector or "Financial Services"
    if not os.path.isfile(path):
        print("ABORT: %s not found." % path)
        return 1

    try:
        import pdfplumber
    except ImportError:
        print("ABORT: pdfplumber is needed.")
        print("       pip install pdfplumber --break-system-packages")
        return 1

    rows, skipped_header, skipped_blank = [], 0, 0
    with pdfplumber.open(path) as pdf:
        pages = len(pdf.pages)
        for page in pdf.pages:
            for table in (page.extract_tables() or []):
                for cells in table:
                    cells = [c for c in cells]
                    if len(cells) < 3:
                        continue
                    # The number column is optional - some pages drop it.
                    if re.fullmatch(r"\d{1,3}", _flat(cells[0])):
                        name, loc, contact = (_flat(cells[1]),
                                              _flat(cells[2]) if len(cells) > 2 else "",
                                              _flat(cells[3]) if len(cells) > 3 else "")
                        date = _flat(cells[4]) if len(cells) > 4 else ""
                    else:
                        name, loc, contact = (_flat(cells[0]),
                                              _flat(cells[1]) if len(cells) > 1 else "",
                                              _flat(cells[2]) if len(cells) > 2 else "")
                        date = _flat(cells[3]) if len(cells) > 3 else ""

                    low = name.lower()
                    if not name:
                        skipped_blank += 1
                        continue
                    if any(low.startswith(h) for h in HEADERS) or len(name) < 4:
                        skipped_header += 1
                        continue

                    blob = " ".join(x for x in (contact, loc) if x)
                    email = EMAIL.search(blob)
                    phone = PHONE.search(blob)
                    postal = POSTAL.search(blob)
                    rows.append({
                        "company_name": name,
                        "industry_description": ("%s - %s" % (label, sector)
                                                 if label else sector),
                        "town": _town(loc, contact),
                        "company_phone": re.sub(r"\s+", " ",
                                                phone.group(1)).strip(" ,") if phone else "",
                        "company_email": email.group(0) if email else "",
                        "contact_name": "",
                        "postal_address": _flat(postal.group(1)) if postal else "",
                        # The location cell is the street address; the contact
                        # cell is the postal one. Keeping them apart matters -
                        # an RM visits one and writes to the other.
                        "physical_location": loc,
                        "website": "",
                        "notes": ("Licenced %s" % date) if date else "",
                    })

    if not rows:
        print("ABORT: no rows came out. Run the diagnostic and send it:")
        print("   python scripts\\diag_register_pdf.py %s --page 2"
              % os.path.basename(path))
        return 1

    out = os.path.splitext(os.path.basename(path))[0] + ".csv"
    with open(out, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        for r in rows:
            w.writerow(r)

    have = lambda k: sum(1 for r in rows if str(r.get(k, "")).strip())
    print("=" * 76)
    print("REGISTER EXTRACT (ruled table)")
    print("=" * 76)
    print("  file        %s" % os.path.basename(path))
    print("  pages       %d" % pages)
    print("  EXTRACTED   %d" % len(rows))
    print("  headers     %d skipped" % skipped_header)
    if skipped_blank:
        print("  blank       %d skipped" % skipped_blank)
    print("")
    print("  WHAT CAME WITH THEM")
    for k, lbl in (("company_phone", "phone"), ("company_email", "email"),
                   ("postal_address", "postal box"),
                   ("physical_location", "street address"), ("town", "town")):
        print("     %-16s %d of %d" % (lbl, have(k), len(rows)))

    towns = {}
    for r in rows:
        t = r["town"] or "(no town)"
        towns[t] = towns.get(t, 0) + 1
    print("\n  TOP TOWNS")
    for t, n in sorted(towns.items(), key=lambda x: -x[1])[:8]:
        print("     %-22s %d" % (t, n))

    print("\n  SAMPLE - check EVERY field, not just the name")
    for r in rows[:4]:
        print("\n     Name     : %s" % r["company_name"])
        print("     Phone    : %s" % (r["company_phone"] or "(none)"))
        print("     Email    : %s" % (r["company_email"] or "(none)"))
        print("     Street   : %s" % (r["physical_location"][:52] or "(none)"))
        print("     Postal   : %s  [%s]" % (r["postal_address"][:34] or "(none)",
                                            r["town"] or "no town"))

    print("\n\nwrote %s" % out)
    print("\nREAD THE SAMPLE. If a name looks like a street, or a phone looks")
    print("like a box number, send me the four blocks above rather than")
    print("importing - it is far cheaper to fit the parser than to clean %d"
          % len(rows))
    print("records afterwards.")
    print("\nIf it looks right:")
    print("   python scripts\\import_business_register.py %s --apply \\" % out)
    print("       --source \"CBK directory of licenced foreign exchange bureaus\" \\")
    print("       --licence \"published register\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
