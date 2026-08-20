#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Read a CBK-style directory - numbered blocks with labelled lines.

SASRA publishes a table. CBK publishes blocks:

    1.  Caritas Microfinance Bank Limited
    Chief Executive Officer: Mr. George Mugwe Maina
    Postal Address: P. O. Box 15352 - 00100, Nairobi
    Telephone: +254 - 020 - 5151500
    E-mail: info@caritas-mfb.co.ke
    Website: www.caritas-mfb.co.ke
    Physical Address: Cardinal Maurice Otunga Plaza, Ground Floor, Kaunda
    Street, Nairobi.
    Date Licenced: 2nd June 2015
    Branches: 1

Which is the richest source yet - a named person, a phone, an email, a website
and a street address, where SASRA gave a name and a postal box.

    python scripts\\extract_directory_blocks.py cbk_mfb.pdf --label "Microfinance bank"
    python scripts\\extract_directory_blocks.py cbk_mfb.txt --label "Microfinance bank"

TAKES A PDF OR A TEXT FILE. If the page will not download - CBK renders some
directories by script - copy the text into a .txt and pass that. The parser
does not care where the words came from.

WHAT IT WILL NOT DO: guess. A block with no name is reported, not invented, and
the running header "DIRECTORY OF LICENCED MICROFINANCE BANKS" is recognised and
dropped rather than becoming an institution.

Writes a CSV in the shape import_business_register.py reads.
"""
import csv
import os
import re
import sys

LABELS = {
    "postal": ("postal address",),
    "phone": ("telephone", "tel", "mobile"),
    "email": ("e-mail", "email"),
    "website": ("website", "web"),
    "physical": ("physical address", "location"),
    "contact": ("chief executive officer", "managing director",
                "ag. chief executive officer", "general manager",
                "acting chief executive officer"),
    "licenced": ("date licenced", "date licensed"),
    "branches": ("branches",),
}

# A line that is a running header or a bare page number, not an institution.
NOISE = re.compile(r"^(directory of|list of|schedule|page\b|\d{1,3}\s*$)", re.I)

COUNTIES = ["Nairobi", "Mombasa", "Kisumu", "Nakuru", "Uasin Gishu", "Eldoret",
            "Kiambu", "Machakos", "Kajiado", "Nyeri", "Meru", "Kakamega",
            "Bungoma", "Kilifi", "Kericho", "Kitale", "Nyandarua", "Muranga",
            "Embu", "Kirinyaga", "Laikipia", "Narok", "Bomet", "Kisii",
            "Nyamira", "Migori", "Homa Bay", "Siaya", "Busia", "Vihiga",
            "Thika", "Naivasha", "Malindi", "Nanyuki", "Kitui", "Makueni"]


def _text(path):
    if path.lower().endswith(".pdf"):
        try:
            import pdfplumber
        except ImportError:
            print("ABORT: pdfplumber is needed for a PDF.")
            print("       pip install pdfplumber --break-system-packages")
            print("       Or copy the text into a .txt and pass that instead.")
            return None
        out = []
        with pdfplumber.open(path) as pdf:
            for page in pdf.pages:
                out.append(page.extract_text() or "")
        return "\n".join(out)
    return open(path, encoding="utf-8", errors="ignore").read()


def _label_of(line):
    low = line.lower().lstrip()
    for key, words in LABELS.items():
        for w in words:
            if low.startswith(w + ":") or low.startswith(w + " :"):
                return key, line.split(":", 1)[1].strip()
    return None, ""


def _town(*bits):
    blob = " ".join(b for b in bits if b)
    for c in COUNTIES:
        if re.search(r"\b%s\b" % re.escape(c), blob, re.I):
            return "Uasin Gishu" if c.lower() == "eldoret" else c
    return ""


def main():
    if len(sys.argv) < 2 or sys.argv[1].startswith("--"):
        print("ABORT: give the file, e.g.")
        print("   python scripts\\extract_directory_blocks.py cbk_mfb.txt \\")
        print("       --label \"Microfinance bank\"")
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

    text = _text(path)
    if text is None:
        return 1

    lines = [l.rstrip() for l in text.split("\n")]
    # A new entry begins at "1.  Name" / "12. Name".
    start = re.compile(r"^\s*(\d{1,3})[.)]\s+(.{4,})$")

    entries, cur, pending = [], None, None
    for raw in lines:
        line = raw.strip()
        if not line:
            continue
        m = start.match(line)
        if m and not NOISE.match(m.group(2)):
            if cur:
                entries.append(cur)
            cur = {"name": m.group(2).strip(), "no": m.group(1)}
            pending = None
            continue
        if cur is None:
            continue
        if NOISE.match(line):
            continue
        key, val = _label_of(line)
        if key:
            cur[key] = val
            pending = key
        elif pending in ("physical", "postal", "email", "phone"):
            # A wrapped value - "Kaunda Street," then "Nairobi." on its own
            # line. Rejoin rather than drop, or half the street addresses go.
            cur[pending] = (cur.get(pending, "") + " " + line).strip()
    if cur:
        entries.append(cur)

    rows, noname = [], 0
    for e in entries:
        name = re.sub(r"\s+", " ", e.get("name", "")).strip(" .")
        if len(name) < 4:
            noname += 1
            continue
        town = _town(e.get("physical", ""), e.get("postal", ""))
        email = e.get("email", "")
        # A directory often lists three; the first is the one to write to.
        email = re.split(r"[;,]", email)[0].strip()
        phone = e.get("phone", "")
        phone = re.split(r"[;,/]", phone)[0].strip()
        rows.append({
            "company_name": name,
            "industry_description": "%s - %s" % (label, sector) if label else sector,
            "town": town,
            "company_phone": phone,
            "company_email": email,
            "contact_name": e.get("contact", ""),
            "postal_address": e.get("postal", ""),
            "physical_location": e.get("physical", ""),
            "website": e.get("website", ""),
            "notes": " ".join(x for x in (
                ("Licenced %s" % e["licenced"]) if e.get("licenced") else "",
                ("%s branch(es)" % e["branches"]) if e.get("branches") else "",
            ) if x).strip(),
        })

    out = os.path.splitext(os.path.basename(path))[0] + ".csv"
    with open(out, "w", encoding="utf-8-sig", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()) if rows else
                           ["company_name"])
        w.writeheader()
        for r in rows:
            w.writerow(r)

    have = lambda k: sum(1 for r in rows if str(r.get(k, "")).strip())
    print("=" * 76)
    print("DIRECTORY EXTRACT")
    print("=" * 76)
    print("  file        %s" % os.path.basename(path))
    print("  blocks      %d" % len(entries))
    print("  EXTRACTED   %d" % len(rows))
    if noname:
        print("  no name     %d (reported, not invented)" % noname)
    print("")
    print("  WHAT CAME WITH THEM")
    for k, lbl in (("contact_name", "a named person"), ("company_phone", "phone"),
                   ("company_email", "email"), ("website", "website"),
                   ("physical_location", "street address"), ("town", "town")):
        print("     %-16s %d of %d" % (lbl, have(k), len(rows)))

    print("\n  SAMPLE - check EVERY field, not just the name")
    for r in rows[:3]:
        print("\n     Name     : %s" % r["company_name"])
        print("     Person   : %s" % (r["contact_name"] or "(none)"))
        print("     Phone    : %s" % (r["company_phone"] or "(none)"))
        print("     Email    : %s" % (r["company_email"] or "(none)"))
        print("     Location : %s  [%s]" % (r["physical_location"][:44] or "(none)",
                                            r["town"] or "no town"))

    print("\n\nwrote %s" % out)
    print("\nIf the sample looks right:")
    print("   python scripts\\import_business_register.py %s --apply \\" % out)
    print("       --source \"CBK directory of licenced microfinance banks\" \\")
    print("       --licence \"published register\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
