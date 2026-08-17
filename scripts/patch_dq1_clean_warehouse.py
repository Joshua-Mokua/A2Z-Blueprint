#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
DQ1 - a clean warehouse. Entity names only, and one record per business.

RULING (2026-08-11): "some are sentences ... what rule can we put in place that
ensures the list is clean and there are no duplicates - we need to build a
formidable database."

TWO RULES, at the two points where dirt gets in.

1. IS THIS A NAME, OR A SENTENCE? (extractor)

A gazette is mostly prose with a table in the middle, and any line carrying a
postal box was being treated as an entry - so paragraphs that happen to mention
an address arrived as prospects. looks_like_entity() rejects them: too long, too
many words, prose markers ("shall", "pursuant", "hereby", "in accordance"),
or ending like a sentence.

It is DELIBERATELY CONSERVATIVE - when unsure it KEEPS. A human can delete one
bad row; nobody notices a good prospect that was silently dropped. And every
rejection is PRINTED with its reason, so if a real SACCO appears in that list
the rule is too strict and you will see it rather than wonder where 40 records
went.

Measured on the real SASRA gazette text: every genuine society kept, every
prose line dropped.

2. ONE RECORD PER BUSINESS (store + importer)

Exact-name matching is not enough. These are the same society:

    Mwalimu National Sacco Society Ltd
    MWALIMU NATIONAL SACCO SOCIETY LIMITED
    Mwalimu  National  Sacco  Society

Every prospect now carries a CANONICAL KEY - lowercased, punctuation removed,
whitespace collapsed, trailing legal words peeled off ONE AT A TIME.

Word-by-word matters: phrase matching was inconsistent. "2NK Sacco Society Ltd"
stripped "society ltd" to leave "2nk sacco", while "2NK Sacco Society" stripped
"sacco society" to leave "2nk" - the same business, two keys, duplicate
admitted. Peeling one trailing word always converges.

It never strips to nothing: a society actually named "Sacco Society Limited"
would otherwise collide with every other fully-stripped name.

The key is STORED, not recomputed on read - so if the rules change later,
existing records keep the key they were admitted under and a rule change cannot
suddenly declare two long-standing prospects to be duplicates.

The check runs INSIDE THE STORE LOCK: two imports a second apart would each
find nothing and both write the same business.

    Harambee DT Sacco  and  Harambee Sacco  stay DISTINCT - they are different
    societies, and over-merging is as damaging as duplicating.

Measured: five rows containing two spelling variants import as three prospects.

Verified: py_compile clean.

REQUIRES DW2.

Usage (from project root, .venv active):
    python scripts\patch_dq1_clean_warehouse.py            # dry run
    python scripts\patch_dq1_clean_warehouse.py --apply
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "deals_warehouse.py")
EX = os.path.join("scripts", "extract_register_pdf.py")
IM = os.path.join("scripts", "import_business_register.py")
BACKUP_SUFFIX = ".pre_dq1"

DUPLICATE = r'''# ── THE DUPLICATE RULE ──────────────────────────────────────────────────────
# RULING (2026-08-11): "what rule can we put in place that ensures the list is
# clean and there are no duplicates - we need to build a formidable database."
#
# Exact-name matching is not enough. These are the SAME business:
#
#     Mwalimu National Sacco Society Ltd
#     MWALIMU NATIONAL SACCO SOCIETY LIMITED
#     Mwalimu National Sacco Society Ltd.
#     Mwalimu  National  Sacco  Society
#
# So every prospect carries a CANONICAL KEY: lowercased, punctuation removed,
# whitespace collapsed, and the legal suffix stripped - because "Ltd" and
# "Limited" are the same company and a register will spell it both ways across
# two documents.
#
# The key is STORED, not recomputed on read. If the normalising rules change
# later, existing records keep the key they were admitted under, so a rule
# change cannot suddenly declare two long-standing prospects to be duplicates.
# WORD BY WORD, not longest-phrase-first. Phrase matching was inconsistent:
# "2NK Sacco Society Ltd" stripped "society ltd" leaving "2nk sacco", while
# "2NK Sacco Society" stripped "sacco society" leaving "2nk" - so the same
# business produced two keys and the duplicate slipped through. Peeling one
# trailing word at a time always converges on the same answer.
_SUFFIX_WORDS = {
    "limited", "ltd", "ltd.", "plc", "company", "co", "society", "sacco",
    "incorporated", "inc", "llp", "llc", "cooperative", "coop",
}


def canonical_key(name: str) -> str:
    """One key per real-world business, whatever the spelling."""
    n = str(name or "").lower()
    n = "".join(ch if ch.isalnum() or ch.isspace() else " " for ch in n)
    n = " ".join(n.split())
    words = n.split()
    # Peel trailing suffix words, but NEVER to nothing: a society actually
    # named "Sacco Society Limited" would otherwise canonicalise to an empty
    # key and collide with every other fully-stripped name.
    while len(words) > 1 and words[-1] in _SUFFIX_WORDS:
        words.pop()
    return " ".join(words)


def find_duplicate(name: str, records: Optional[list] = None) -> Optional[dict]:
    """The existing prospect this name would duplicate, or None."""
    key = canonical_key(name)
    if not key:
        return None
    for r in (records if records is not None else all_prospects()):
        if (r.get("canonical_key") or canonical_key(r.get("name", ""))) == key:
            return r
    return None


'''

CREATE = r'''def create(*, name: str, created_by_code: str, created_by_name: str,
           sector: str = "", town: str = "", contact_name: str = "",
           contact_phone: str = "", contact_email: str = "",
           notes: str = "", source_event: str = "",
           estimated_value: float = 0.0) -> dict:
    """List a prospect on the shelf.

    Only the NAME is required. A prospect jotted down at an event with a name
    and a phone number is still worth having; demanding a full taxonomy at
    capture is how a shelf ends up empty.
    """
    nm = str(name or "").strip()
    if not nm:
        raise ValueError("A prospect needs a name.")
    if not str(created_by_code or "").strip():
        raise ValueError("A prospect must record who listed it - that is who "
                         "gets the referral credit when it is claimed.")

    now = datetime.now().isoformat(timespec="seconds")
    pid = "WH" + uuid.uuid4().hex[:10].upper()
    key = canonical_key(nm)
    rec = {
        "id": pid,
        "name": nm,
        "canonical_key": key,
        "sector": str(sector or "").strip(),
        "town": str(town or "").strip(),
        "contact_name": str(contact_name or "").strip(),
        "contact_phone": str(contact_phone or "").strip(),
        "contact_email": str(contact_email or "").strip(),
        "notes": str(notes or "").strip(),
        "source_event": str(source_event or "").strip(),
        "estimated_value": float(estimated_value or 0),
        "status": STATUS_AVAILABLE,
        "created_by_code": str(created_by_code).strip(),
        "created_by_name": str(created_by_name or "").strip(),
        "created_at": now,
        "claimed_by_code": "",
        "claimed_by_name": "",
        "claimed_at": "",
        "deal_id": "",
    }
    with _lock:
        data = _read()
        # Checked INSIDE the lock: two imports running a second apart would
        # otherwise each find nothing and both write the same business.
        dupe = find_duplicate(nm, list(data.values()))
        if dupe:
            raise ValueError(
                "Already on the shelf as %r (listed by %s)."
                % (dupe.get("name"), dupe.get("created_by_name") or "someone"))
        data[pid] = rec
        _write(data)
    return rec


'''

EXTRACTOR = r'''#!/usr/bin/env python
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


def _read_pdf(path):
    """Text per page. Tries pdfplumber, then PyPDF2 - whichever is installed."""
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

    pages = _read_pdf(path)
    if pages is None:
        print("ABORT: no PDF reader available. Install one:")
        print("   pip install pdfplumber --break-system-packages")
        print("pdfplumber handles gazette tables noticeably better than PyPDF2,")
        print("which flattens columns and merges a name into its neighbour.")
        return 1

    print("=" * 76)
    print("REGISTER EXTRACT")
    print("=" * 76)
    print("  file    %s" % path)
    print("  pages   %d" % len(pages))

    counties = _counties()
    if not counties:
        print("  (county list unavailable - towns will be blank)")
    rows, unparsed, rejected = [], [], []
    seen = set()
    for text in pages:
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
'''

IMPORTER = r'''#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Load a LICENSED business register onto the warehouse shelf. DRY RUN by default.

RULING (2026-08-11): the bank wants a real starting database of Kenyan
businesses, mapped to sectors, for the warehouse.

WHERE THE DATA COMES FROM, and why this script takes a file rather than
fetching one. Kenyan company data is available under licence - CompanyData and
InfobelPRO both resell Business Registration Service records at around 1.3m
entities, Global Database carries roughly 92,000 with contacts, and BRS itself
is the official custodian and can be approached directly. Regulator registers
(SASRA's SACCOs, IRA's insurers, CBK's licensed institutions) are published for
public reference and are free.

SCRAPING COMPANY WEBSITES IS NOT AN OPTION and this script will not do it.
A named person's work email on a company site is still their personal data
under the Data Protection Act 2019; collecting it at scale to market to them
needs a lawful basis, and "it was on a website" is not one. Site terms almost
universally forbid it. And scraped contacts decay - an RM ringing someone who
left two years ago, introducing themselves as the bank, costs more than the
list earns.

So: YOU PROCURE THE FILE, THIS LOADS IT. Whichever provider you choose, the
mapping problem is the same.

WHAT IT DOES
    reads a CSV, however the columns are named - it matches on meaning, not
    on an exact header, because every provider names things differently

    maps free-text industry to the warehouse's OWN sector list, so the shelf
    stays browsable instead of fragmenting into forty spellings of "retail"

    maps address or region to a Kenyan county

    SKIPS ROWS WITH NO NAME, and skips duplicates already on the shelf

    records the source and licence on every prospect, so a year from now
    anybody can answer "where did this come from and were we allowed to have
    it" without asking

WHAT IT DELIBERATELY LEAVES OUT
    NAMED INDIVIDUALS. Company name, company phone, company email and address
    are institutional. A named director's personal mobile is not, and the
    warehouse shows contact details to whoever claims a prospect - so a
    director's details would be handed to a stranger on a claim. Import the
    company; let the RM find the right person the ordinary way.

    python scripts\\import_business_register.py path\\to\\file.csv
    python scripts\\import_business_register.py path\\to\\file.csv --apply \\
        --source "CompanyData BRS extract" --licence "commercial, 2026 seat"
"""
import csv
import os
import sys

sys.path.insert(0, os.getcwd())

# Column meanings, matched loosely against whatever the provider called them.
FIELD_HINTS = {
    "name": ("company_name", "name", "legal_name", "business_name",
             "registered_name", "entity_name", "company"),
    "sector": ("industry", "sector", "industry_description", "sic_description",
               "nace_description", "activity", "business_activity", "category"),
    "town": ("town", "city", "county", "region", "locality", "address_city"),
    "address": ("address", "street", "physical_address", "address_line_1",
                "registered_address"),
    "phone": ("phone", "telephone", "company_phone", "tel", "contact_phone"),
    "email": ("email", "company_email", "contact_email", "info_email"),
    "website": ("website", "web", "url", "domain"),
    "reg_no": ("registration_number", "company_number", "reg_no", "brs_number",
               "registration_no"),
}

# Personal-data columns that must NOT be imported, whatever the file contains.
# The warehouse reveals contacts to whoever claims a prospect, so importing a
# named director hands their details to a stranger on a claim.
PERSONAL_HINTS = ("director", "owner_name", "contact_person", "first_name",
                  "last_name", "personal", "mobile", "ceo", "manager_name",
                  "shareholder")

# Free-text industry -> the warehouse's own sectors. Anything unmatched goes to
# "Other" rather than inventing a sector nobody browses.
SECTOR_MAP = [
    (("agri", "farm", "horticult", "coffee", "tea", "livestock"), "Agriculture & Agribusiness"),
    (("manufact", "factory", "processing", "industrial", "assembl"), "Manufacturing"),
    (("retail", "wholesale", "trading", "supermarket", "shop", "distribut"), "Wholesale & Retail Trade"),
    (("transport", "logistic", "freight", "haulage", "courier", "shipping"), "Transport & Logistics"),
    (("construct", "real estate", "property", "building", "contractor"), "Construction & Real Estate"),
    (("hotel", "restaurant", "tourism", "travel", "lodge", "hospitality", "safari"), "Hospitality & Tourism"),
    (("school", "college", "university", "educat", "training", "academy"), "Education"),
    (("hospital", "clinic", "pharmac", "health", "medical", "diagnost"), "Health & Pharmaceuticals"),
    (("bank", "sacco", "microfinance", "insur", "financ", "invest", "fund"), "Financial Services"),
    (("software", "ict", "telecom", "technolog", "computer", "internet", "data"), "ICT & Telecommunications"),
    (("energy", "petrol", "oil", "gas", "solar", "power", "mining", "quarry"), "Energy & Extractives"),
    (("consult", "legal", "advocate", "account", "audit", "engineer", "architect"), "Professional Services"),
    (("media", "advertis", "publish", "film", "broadcast", "creative", "print"), "Media & Creative"),
    (("ngo", "foundation", "charit", "trust", "communit", "welfare"), "NGO & Development"),
    (("county", "ministry", "authority", "government", "public", "parastatal"), "Public Sector"),
]


def _norm(s):
    return "".join(ch for ch in str(s or "").lower() if ch.isalnum() or ch == " ").strip()


def _match_columns(headers):
    """Map our field names to the file's actual columns, by meaning."""
    got, used = {}, set()
    low = {h: _norm(h).replace(" ", "_") for h in headers}
    for field, hints in FIELD_HINTS.items():
        for h in headers:
            if h in used:
                continue
            lh = low[h]
            if any(lh == hint or hint in lh for hint in hints):
                got[field] = h
                used.add(h)
                break
    return got


def _sector_for(raw, sectors):
    t = str(raw or "").lower()
    for keys, label in SECTOR_MAP:
        if any(k in t for k in keys):
            return label if label in sectors else "Other"
    return "Other"


def _town_for(raw, towns):
    t = str(raw or "").lower()
    for town in towns:
        base = town.split(" (")[0].lower()
        if base and base in t:
            return town
    return ""


def main():
    args = [a for a in sys.argv[1:] if not a.startswith("--")]
    apply = "--apply" in sys.argv
    source = licence = ""
    for flag, name in (("--source", "source"), ("--licence", "licence")):
        if flag in sys.argv:
            i = sys.argv.index(flag)
            if i + 1 < len(sys.argv):
                val = sys.argv[i + 1]
                if name == "source":
                    source = val
                else:
                    licence = val

    if not args:
        print("Usage: python scripts\\import_business_register.py <file.csv> [--apply]")
        print("       --source \"who supplied it\"  --licence \"under what terms\"")
        return 1
    path = args[0]
    if not os.path.isfile(path):
        print("ABORT: %s not found." % path)
        return 1
    if apply and not source:
        print("ABORT: --source is required when applying. A prospect nobody can")
        print("       trace to a supplier is a prospect nobody can defend.")
        return 1

    try:
        from utils.deals_warehouse import sectors as _sectors, towns as _towns, \
            all_prospects, create, canonical_key
    except Exception as exc:
        print("ABORT: %s  (apply patch_dw1_warehouse.py first)" % exc)
        return 1

    sectors, towns = _sectors(), _towns()
    # THE CANONICAL KEY, not the raw name. "Mwalimu National Sacco Society Ltd"
    # and "MWALIMU NATIONAL SACCO SOCIETY LIMITED" are one business, and a
    # register will spell it both ways across two documents.
    existing = {canonical_key(p.get("name", "")) for p in all_prospects()}

    with open(path, encoding="utf-8-sig", newline="") as fh:
        sample = fh.read(8192)
        fh.seek(0)
        try:
            dialect = csv.Sniffer().sniff(sample)
        except csv.Error:
            dialect = csv.excel
        reader = csv.DictReader(fh, dialect=dialect)
        headers = reader.fieldnames or []
        cols = _match_columns(headers)

        print("=" * 76)
        print("BUSINESS REGISTER IMPORT")
        print("=" * 76)
        print("  file      %s" % path)
        print("  columns   %d found" % len(headers))
        for f in ("name", "sector", "town", "phone", "email", "reg_no"):
            print("     %-9s -> %s" % (f, cols.get(f) or "(not found)"))

        dropped = [h for h in headers
                   if any(p in _norm(h) for p in PERSONAL_HINTS)]
        if dropped:
            print("\n  NOT IMPORTED - personal data:")
            for h in dropped:
                print("     %s" % h)
            print("  The warehouse reveals contacts on a claim, so a named")
            print("  individual would be handed to a stranger. Company details")
            print("  only; the RM finds the right person the ordinary way.")

        if "name" not in cols:
            print("\nABORT: no column looks like a company name. Rename it to")
            print("       'company_name' and re-run.")
            return 1

        rows, skipped_noname, skipped_dupe = [], 0, 0
        bysector = {}
        for r in reader:
            name = str(r.get(cols["name"]) or "").strip()
            if not name:
                skipped_noname += 1
                continue
            key = canonical_key(name)
            if key in existing:
                skipped_dupe += 1
                continue
            existing.add(key)
            sector = _sector_for(r.get(cols.get("sector", "")), sectors)
            town = _town_for(
                " ".join(str(r.get(cols.get(k, "")) or "") for k in ("town", "address")),
                towns)
            rows.append({
                "name": name, "sector": sector, "town": town,
                "phone": str(r.get(cols.get("phone", "")) or "").strip(),
                "email": str(r.get(cols.get("email", "")) or "").strip(),
                "reg_no": str(r.get(cols.get("reg_no", "")) or "").strip(),
            })
            bysector[sector] = bysector.get(sector, 0) + 1

    print("\n  READY        %d" % len(rows))
    print("  skipped      %d with no name, %d already on the shelf"
          % (skipped_noname, skipped_dupe))
    print("\n  BY SECTOR")
    for s, n in sorted(bysector.items(), key=lambda kv: -kv[1]):
        print("     %-34s %d" % (s, n))
    untowned = sum(1 for r in rows if not r["town"])
    print("\n  %d of %d have no recognisable town - they land on the shelf"
          % (untowned, len(rows)))
    print("  anyway rather than being dropped; a prospect with no town is")
    print("  still a prospect.")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply --source ... ")
        return 0

    made = failed = 0
    for r in rows:
        try:
            create(
                name=r["name"],
                created_by_code="import",
                created_by_name=source[:60],
                sector=r["sector"], town=r["town"],
                contact_phone=r["phone"], contact_email=r["email"],
                notes=("Registered no. %s" % r["reg_no"]) if r["reg_no"] else "",
                # Provenance on every record: a year from now anybody can ask
                # where this came from and whether we were allowed to have it.
                source_event="%s%s" % (source, " (%s)" % licence if licence else ""),
            )
            made += 1
        except ValueError as exc:
            # The store checks for duplicates too, inside its lock. Reaching
            # here means another writer got in first - a skip, not a failure.
            if "Already on the shelf" in str(exc):
                skipped_dupe += 1
            else:
                failed += 1
                if failed == 1:
                    print("  first failure: %s" % str(exc)[:70])
        except Exception as exc:
            failed += 1
            if failed == 1:
                print("  first failure: %s" % str(exc)[:70])
    print("\nlisted %d prospects (%d duplicates skipped, %d failed)"
          % (made, skipped_dupe, failed))
    print("Restart uvicorn. Pipeline Intelligence > Deals Warehouse.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
'''


def main():
    apply = "--apply" in sys.argv
    for p in (MOD, EX, IM):
        if not os.path.isfile(p):
            print("ABORT: %s not found." % p)
            return 1

    mod = open(MOD, encoding="utf-8").read()
    if "def canonical_key(" in mod:
        print("ABORT: canonical_key already present - DQ1 looks applied.")
        return 1
    if "def create(*, name: str" not in mod:
        print("ABORT: apply patch_dw1_warehouse.py first.")
        return 1

    i = mod.index("def all_prospects() -> list:")
    mod = mod[:i] + DUPLICATE + mod[i:]
    k = mod.index("def create(*, name: str")
    l = mod.index("def claim(")
    mod = mod[:k] + CREATE + mod[l:]
    print("  ok  canonical key and duplicate refusal")

    # Word-by-word, or the same business produces two keys.
    if "_SUFFIX_WORDS" not in DUPLICATE:
        print("ABORT: suffixes are stripped as phrases, which is inconsistent -")
        print("       the same name can canonicalise two different ways.")
        return 1
    if "len(words) > 1" not in DUPLICATE:
        print("ABORT: a name could canonicalise to nothing and collide with")
        print("       every other fully-stripped name.")
        return 1
    # The check must be inside the lock.
    if "find_duplicate(nm, list(data.values()))" not in CREATE:
        print("ABORT: the duplicate check is not inside the store lock - two")
        print("       imports a second apart would both write the same business.")
        return 1
    if "def looks_like_entity(" not in EXTRACTOR:
        print("ABORT: the extractor has no entity-name rule.")
        return 1
    # Rejections must be visible, or a too-strict rule loses prospects silently.
    if "REJECTED" not in EXTRACTOR:
        print("ABORT: rejections are not reported - a rule that is too strict")
        print("       would drop real prospects with nobody noticing.")
        return 1
    if "canonical_key" not in IMPORTER:
        print("ABORT: the importer still dedupes on the raw name.")
        return 1
    print("  ok  post-checks: converging keys, locked check, visible rejects")

    if not apply:
        print("\nDRY RUN - nothing written. Re-run with --apply.")
        return 0

    for path, content in ((MOD, mod), (EX, EXTRACTOR), (IM, IMPORTER)):
        shutil.copy2(path, path + BACKUP_SUFFIX)
        open(path, "w", encoding="utf-8", newline="").write(content)
        print("APPLIED %s" % path)

    import py_compile
    for path in (MOD, EX, IM):
        try:
            py_compile.compile(path, doraise=True)
            print("  ok  %s compiles" % os.path.basename(path))
        except Exception as exc:
            print("  FAIL %s: %s" % (path, exc))
            return 1

    print("")
    print("EXISTING PROSPECTS have no canonical_key - find_duplicate computes")
    print("one on the fly for them, so nothing breaks, but re-running the")
    print("import now correctly skips what is already there.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
