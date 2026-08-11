#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Turn a published regulator register (PDF) into a CSV the warehouse can import.

RULING (2026-08-11): a clean database of real Kenyan businesses for the
warehouse.

WHAT THIS IS FOR. Kenya's financial regulators publish their licensed-entity
registers by law, for public reference - SASRA's SACCOs, CBK's banks and forex
bureaus, IRA's insurers and brokers, RBA's pension schemes. They arrive as
gazette PDFs with names and postal or physical addresses. Institutional data,
published for exactly this kind of use, no licence question at all.

BE REALISTIC ABOUT VOLUME. Across every free register you will get somewhere
around 1,800 records:

    SASRA      ~352  (176 deposit-taking + 176 non-deposit-taking, 2026)
    RBA        ~1000 pension schemes
    IRA        ~260  insurers and brokers
    CBK        ~100  banks, forex bureaus, microfinance
    NSE        ~60   listed companies

Real, addressed, and genuinely good bank prospects - but NOT ten thousand.
Reaching ten thousand means licensed BRS data from a provider; that is a
procurement decision, and scripts/import_business_register.py already reads
whatever they deliver. This script exists so the free tier is actually used
rather than talked about.

HOW IT READS A GAZETTE. These PDFs are tables rendered as text: a name, then an
address, often split across lines. The parser looks for a POSTAL BOX pattern
("P.O. Box 1325 - 00200, Kajiado") because that is the one reliable anchor -
names vary wildly, addresses do not. Everything before the box on the same
record is the name; the town is whatever follows the postal code.

IT REPORTS WHAT IT COULD NOT PARSE rather than silently dropping it. A register
that yields 140 rows from a 176-entry schedule is a parsing problem, and you
should see that before you import.

    python scripts\\extract_register_pdf.py sasra_2026.pdf
    python scripts\\extract_register_pdf.py sasra_2026.pdf --out saccos.csv \\
        --sector "Financial Services" --label "SACCO"
"""
import csv
import os
import re
import sys

sys.path.insert(0, os.getcwd())

# Every variant the real SASRA 2026 gazette actually uses - checked against the
# published document, not assumed:
#     "P.O. Box 1325 – 00200, Kajiado"      "P.O Box 11607 – 00400, Nairobi."
#     "P.0 Box 80 – 20103, Eldama Ravine"   <- DIGIT ZERO, not the letter O
#     "P.O Box 94 – 40107 Muhoroni"         <- no comma
#     "P.O Box Private Bag–40100, Koru"     "Private Bag 20157, Nakuru"
# A stricter pattern silently dropped every entry using one of these.
BOX = re.compile(
    r"P\s*[.\s]*[O0]\s*[.\s]*Box\s+(?:Private\s+Bag[\s–-]*)?([0-9]+)?"
    r"\s*[-–—]?\s*([0-9]{4,5})|Private\s+Bag\s+([0-9]{4,5})",
    re.IGNORECASE)

# Lines that are page furniture, not entries.
NOISE = re.compile(
    r"(schedule|pursuant|regulation|authority|gazette|page\s+\d+|p\.?o\.?\s*box\s*$"
    r"|www\.|http|^\s*\d+\s*$|regulations,|hereby publishes|the act"
    r"|names of the|postal address|physical location|county\s*$|further caution"
    r"|dated at|tel:|email:|toll-free|l\.n\.|cap \d)",
    re.IGNORECASE)


# ── IS THIS A COMPANY NAME, OR A SENTENCE? ──────────────────────────────────
# A gazette is mostly prose with a table in the middle. Any line carrying a
# postal box gets treated as an entry, so paragraphs that happen to mention an
# address arrive as "prospects" - and a warehouse full of sentences is worse
# than an empty one, because somebody has to clean it by hand later.
#
# An entity name is SHORT, has FEW COMMON WORDS, and usually carries a legal
# suffix. Prose fails all three.
ENTITY_MARKERS = (
    "sacco", "society", "ltd", "limited", "plc", "company", "co-op",
    "cooperative", "co operative", "bank", "insurance", "assurance", "trust",
    "holdings", "group", "enterprises", "agencies", "services", "investments",
    "union", "association", "scheme", "fund", "brokers", "consultants",
)
# Words that mean prose. "the" alone is not enough - "The Noble Sacco" is real.
PROSE_MARKERS = (
    " shall ", " hereby ", " pursuant ", " which ", " thereof ", " herein ",
    " provided ", " prohibited ", " accordance ", " regulation ", " section ",
    " period commencing ", " is required ", " are duly ", " has been ",
    " undertaking ", " thereunder ", " whose ", " and/or ", " any person ",
    " it is an offence ",
)


def looks_like_entity(name: str) -> tuple:
    """(ok, why not). Conservative: when unsure, KEEP - a human can delete one
    bad row, but nobody notices a good one that was silently dropped."""
    n = " " + str(name or "").strip().lower() + " "
    if len(name) < 4:
        return False, "too short"
    if len(name) > 90:
        return False, "too long to be a name"
    if any(p in n for p in PROSE_MARKERS):
        return False, "reads as prose"
    words = [w for w in name.split() if w]
    if len(words) > 12:
        return False, "%d words" % len(words)
    # A sentence usually ends in a full stop after a lowercase word.
    if name.rstrip().endswith(".") and name.rstrip(".").split()[-1].islower():
        return False, "ends like a sentence"
    if any(m in n for m in ENTITY_MARKERS):
        return True, ""
    # No legal suffix: accept only if it reads like a proper noun phrase -
    # mostly capitalised words, few of them.
    caps = sum(1 for w in words if w[:1].isupper())
    if len(words) <= 8 and caps >= max(1, len(words) - 2):
        return True, ""
    return False, "no entity marker and not a name phrase"


def _counties():
    """Kenya's 47 counties, from the warehouse's own town list.

    THE TOWN IS FOUND BY MATCHING A KNOWN COUNTY, not by reading whatever
    follows the postal code. In the real gazette a line runs

        ... P.O Box 12196 – 10109, Nyeri Kangaru Building, Gakere Road Nyeri

    so "what follows the code" is "Nyeri Kangaru Building" - a plausible-looking
    town that does not exist. The county appears again at the end of the line,
    which is why the LAST match wins.
    """
    try:
        from utils.deals_warehouse import towns
        return [t.split(" (")[0] for t in towns()]
    except Exception:
        return []


def _read_tables(path):
    """Rows from the PDF's TABLES, which is what a gazette register actually is.

    THIS IS THE ONLY RELIABLE WAY TO READ THESE DOCUMENTS. Reading the same
    page as flat text flows the five columns together, so a "name" comes out as
    the previous row's tail plus a header fragment plus part of the real name:

        "Sacco Society Location 145 Shelloyees Regulated Non-WDT"
        "co Nairobi WDT-Sacco robi 65 Hyperflora Regulated Non-WDT"

    Those pass any name rule you care to write - they contain "Sacco" and
    "Society" and look plausible. The rule was never the problem; the
    extraction was.
    """
    try:
        import pdfplumber
    except ImportError:
        return None
    out = []
    with pdfplumber.open(path) as pdf:
        for page in pdf.pages:
            for table in (page.extract_tables() or []):
                for row in table:
                    cells = [(c or "").replace("\n", " ").strip() for c in row]
                    if any(cells):
                        out.append(cells)
    return out


def _read_pdf(path):
    """Text per page - the fallback when tables cannot be detected."""
    try:
        import pdfplumber
        with pdfplumber.open(path) as pdf:
            return [p.extract_text() or "" for p in pdf.pages]
    except ImportError:
        pass
    try:
        from PyPDF2 import PdfReader
        return [(p.extract_text() or "") for p in PdfReader(path).pages]
    except ImportError:
        pass
    try:
        from pypdf import PdfReader
        return [(p.extract_text() or "") for p in PdfReader(path).pages]
    except ImportError:
        return None


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    if not args:
        print("Usage: python scripts\\extract_register_pdf.py <register.pdf>")
        print("       [--out file.csv] [--sector \"Financial Services\"] [--label SACCO]")
        return 1
    path = args[0]
    if not os.path.isfile(path):
        print("ABORT: %s not found." % path)
        return 1

    out = sector = label = ""
    for flag, setter in (("--out", "out"), ("--sector", "sector"), ("--label", "label")):
        if flag in sys.argv:
            i = sys.argv.index(flag)
            if i + 1 < len(sys.argv):
                v = sys.argv[i + 1]
                if setter == "out":
                    out = v
                elif setter == "sector":
                    sector = v
                else:
                    label = v
    out = out or os.path.splitext(path)[0] + ".csv"
    sector = sector or "Financial Services"

    # TABLES FIRST. Only fall back to text when the document has none.
    tables = _read_tables(path)
    pages = None
    if not tables:
        pages = _read_pdf(path)
    if tables is None and pages is None:
        print("ABORT: no PDF reader available. Install one:")
        print("   pip install pdfplumber --break-system-packages")
        print("pdfplumber handles gazette tables noticeably better than PyPDF2,")
        print("which flattens columns and merges a name into its neighbour.")
        return 1

    print("=" * 76)
    print("REGISTER EXTRACT")
    print("=" * 76)
    print("  file    %s" % path)
    print("  pages   %d" % len(pages or []))

    counties = _counties()
    if not counties:
        print("  (county list unavailable - towns will be blank)")
    rows, unparsed, rejected = [], [], []
    seen = set()

    if tables:
        print("  mode    TABLE (%d rows found)" % len(tables))
        for cells in tables:
            # Find the NAME column: the first cell that is neither an index
            # number nor an address. Column order varies between registers, so
            # the shape is inferred per row rather than fixed.
            name = ""
            for c in cells:
                if not c or c.isdigit() or len(c) < 4:
                    continue
                if BOX.search(c):
                    continue
                name = c
                break
            if not name:
                continue
            name = re.sub(r"^\d+[\.\)]?\s+", "", name).strip(" .,-–—")
            # The header row repeats on every page of a gazette and reads like
            # an entity ("Names of the Deposit Taking SACCO Society" contains
            # both "sacco" and "society"), so it must be dropped explicitly.
            if NOISE.search(name):
                continue
            ok, why = looks_like_entity(name)
            if not ok:
                rejected.append((name[:56], why))
                continue
            # The county is usually the LAST populated cell; fall back to
            # matching a known county anywhere in the row.
            town = ""
            tail = [c for c in cells if c]
            if tail:
                cand = tail[-1].strip()
                if cand.lower() in {c.lower() for c in counties}:
                    town = next(c for c in counties if c.lower() == cand.lower())
            if not town:
                joined = " ".join(cells).lower()
                best = -1
                for c in counties:
                    i = joined.rfind(c.lower())
                    if i > best:
                        best, town = i, c
                if best < 0:
                    town = ""
            addr = next((c for c in cells if BOX.search(c)), "")
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "company_name": name,
                "industry_description": ("%s - %s" % (label, sector)) if label else sector,
                "physical_address": addr,
                "town": town,
                "registration_number": "", "company_phone": "", "company_email": "",
            })
        pages = []
    seen = set()
    for text in (pages or []):
        lines = [ln.strip() for ln in (text or "").split("\n") if ln.strip()]
        carry = ""
        for ln in lines:
            if NOISE.search(ln) and not BOX.search(ln):
                carry = ""
                continue
            m = BOX.search(ln)
            if not m:
                # Probably a name awaiting its address on the next line. Only
                # ONE line is carried: a heading two lines above an entry would
                # otherwise be glued onto the front of the first name, which is
                # exactly what happened to "DEPOSIT-TAKING BUSINESS IN KENYA 1.
                # Mwalimu National Sacco".
                if len(ln) > 3 and not ln.isdigit():
                    carry = ln
                continue
            before = ln[:m.start()].strip(" .,-–—")
            name = (carry + " " + before).strip() if carry else before
            carry = ""
            # Strip a leading index number: "12. Mwalimu National Sacco"
            # Entries are numbered "1 ", "19 ", "176 " - with or without a dot.
            # The first version required a dot, so every SASRA row kept its
            # index and every prospect was named "1 2NK Sacco Society Ltd".
            name = re.sub(r"^\d+[\.\)]?\s+", "", name).strip(" .,-–—")
            # A numbered entry begins at its number. Anything before it is
            # page furniture that survived the noise filter.
            m2 = re.search(r"\b\d+[\.\)]\s+(.+)$", name)
            if m2 and len(m2.group(1)) > 3:
                name = m2.group(1).strip(" .,-–—")
            # Last county mentioned on the line - see _counties().
            town = ""
            low = ln.lower()
            best = -1
            for c in counties:
                i = low.rfind(c.lower())
                if i > best:
                    best, town = i, c
            ok, why = looks_like_entity(name)
            if not ok:
                rejected.append((name[:56], why))
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "company_name": name,
                "industry_description": ("%s - %s" % (label, sector)) if label else sector,
                "physical_address": "P.O. Box %s-%s, %s" % (
                    m.group(1) or "", m.group(2) or m.group(3) or "", town),
                "town": town,
                "registration_number": "",
                "company_phone": "",
                "company_email": "",
            })

    print("\n  EXTRACTED   %d entries" % len(rows))
    if rejected:
        print("  REJECTED    %d lines carried an address but are not names:"
              % len(rejected))
        for nm, why in rejected[:8]:
            print("     %-56s (%s)" % (nm, why))
        if len(rejected) > 8:
            print("     ... and %d more" % (len(rejected) - 8))
        print("  Read these. If a real SACCO is in that list the rule is too")
        print("  strict and should be loosened - dropping a genuine prospect")
        print("  silently is the worse failure.")
    if unparsed:
        print("  UNPARSED    %d lines had an address but no usable name" % len(unparsed))

    if not rows:
        print("\nNOTHING EXTRACTED. The parser anchors on a 'P.O. Box NNNN - NNNNN,")
        print("Town' pattern, which this document may not use. Open the PDF and")
        print("check - if the addresses look different, tell me the shape and the")
        print("pattern can be widened rather than guessed at.")
        return 1

    import collections
    bytown = collections.Counter(r["town"] for r in rows if r["town"])
    print("\n  TOP TOWNS")
    for t, n in bytown.most_common(8):
        print("     %-24s %d" % (t[:24], n))
    notown = sum(1 for r in rows if not r["town"])
    if notown:
        print("     (%d with no town)" % notown)

    print("\n  SAMPLE")
    for r in rows[:5]:
        print("     %-46s %s" % (r["company_name"][:46], r["town"]))

    with open(out, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, fieldnames=list(rows[0].keys()))
        w.writeheader()
        w.writerows(rows)
    print("\nwrote %s" % out)
    print("\nCheck the sample above looks like real names, then:")
    print("  python scripts\\import_business_register.py %s" % out)
    print("  python scripts\\import_business_register.py %s --apply \\" % out)
    print("      --source \"SASRA gazette 2026\" --licence \"published register\"")
    return 0


if __name__ == "__main__":
    sys.exit(main())
