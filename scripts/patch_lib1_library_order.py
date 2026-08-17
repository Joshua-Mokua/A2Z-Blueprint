#!/usr/bin/env python
# -*- coding: utf-8 -*-
r"""
LIB1 - the warehouse reads like a library, and names come in clean.

THREE RULINGS (2026-08-11): "it has come with some numbers at the start ...
now it has landed together with the sacco making it a jungle ... this is where
we need to arrange ourselves like a library where one can get into a sector,
subsector or any other better arrangement ... important would also be to
arrange alphabetically on every call."

1. NUMBERS GLUED TO NAMES. RBA prints its row number twice and the PDF glues
   the second copy on: "1Amana Personal Pension Plan", "3Benefits At Work".
   The same doubling can land at the end: "Fahari Retirement Plan 5".

   Stripped only when a CAPITAL follows immediately, so a real name that starts
   with a digit survives - "2NK Sacco Society Ltd" is a genuine society and
   would have been mangled by a blunter rule.

2. SECTOR › SUBSECTOR. Both registers are Financial Services, so loading the
   second one turned one shelf into a heap of SACCOs and pension schemes.
   Prospects now carry a SUBSECTOR taken from the register label, and shelves
   read:

       Financial Services > SACCO
       Financial Services > Pension scheme
       Financial Services > Insurer

   At 1,800 records the top-level category alone tells nobody what they are
   looking at. This is the arrangement that makes the next 1,700 usable rather
   than merely present.

3. ALPHABETICAL, ALWAYS. Newest-first made sense when a shelf held a dozen
   things somebody had just listed. At this size a person is looking for a
   NAME, and a list they cannot scan alphabetically is one they cannot use.
   Shelves themselves are ordered too, so the library has a fixed layout rather
   than one that rearranges itself as data arrives.

Verified: py_compile clean; three registers produce three separate shelves,
alphabetical within each, with "2NK Sacco Society Ltd" intact.

REQUIRES RB1.

Usage (from project root, .venv active):
    python scripts\patch_lib1_library_order.py            # dry run
    python scripts\patch_lib1_library_order.py --apply

Then RE-IMPORT both registers so they pick up their subsector:
    del data\deals_warehouse.json
    python scripts\extract_register_pdf.py sasra_2026.pdf --label SACCO
    python scripts\import_business_register.py sasra_2026.csv --apply ^
        --source "SASRA gazette, 3 February 2026" --licence "published register"
    python scripts\extract_register_pdf.py rba_schemes.pdf --label "Pension scheme"
    python scripts\import_business_register.py rba_schemes.csv --apply ^
        --source "RBA individual retirement benefits schemes" --licence "published register"
"""
import os
import shutil
import sys

MOD = os.path.join("utils", "deals_warehouse.py")
EX = os.path.join("scripts", "extract_register_pdf.py")
IM = os.path.join("scripts", "import_business_register.py")
BACKUP_SUFFIX = ".pre_lib1"

SHELVES = r'''def shelves(status: str = STATUS_AVAILABLE) -> dict:
    """{sector: [prospect, ...]} for browsing, newest first within a shelf.

    Prospects with no sector go to "Unsorted" rather than being hidden - a
    record captured in a hurry is exactly the one somebody should be able to
    find and tidy.
    """
    out: dict = {}
    for rec in all_prospects():
        if status and rec.get("status") != status:
            continue
        # SECTOR › SUBSECTOR, so a shelf reads like a library rather than a
        # heap. At 1,800 records "Financial Services" alone tells nobody
        # whether they are looking at a SACCO, a pension scheme or an insurer.
        sector = str(rec.get("sector") or "").strip() or "Unsorted"
        sub = str(rec.get("subsector") or "").strip()
        key = "%s \u203a %s" % (sector, sub) if sub else sector
        out.setdefault(key, []).append(rec)
    # ALPHABETICAL, always. Newest-first made sense when a shelf held a dozen
    # things somebody had just listed; at this size a person is looking for a
    # NAME, and a list they cannot scan alphabetically is one they cannot use.
    for k in out:
        out[k].sort(key=lambda r: str(r.get("name") or "").lower())
    return dict(sorted(out.items()))

'''

CREATE = r'''def create(*, name: str, created_by_code: str, created_by_name: str,
           sector: str = "", town: str = "", contact_name: str = "",
           contact_phone: str = "", contact_email: str = "",
           notes: str = "", source_event: str = "",
           estimated_value: float = 0.0, subsector: str = "") -> dict:
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
        # SUBSECTOR, so a shelf of 1,800 does not become one heap. "SACCO" and
        # "Pension scheme" are both Financial Services, and a library that
        # stops at the top-level category is a library nobody can walk.
        "subsector": str(subsector or "").strip(),
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
# Registers write an address three ways, all seen in real documents:
#   SASRA   "P.O Box 12196 - 10109, Nyeri"   "P.0 Box 80 – 20103"
#   RBA     "9480-00100"                     bare box and postal code
#   others  "Private Bag 20157"
# A pattern that only knew the first rejected every RBA row as "not an entry".
BOX = re.compile(
    r"P\s*[.\s]*[O0]\s*[.\s]*Box\s+(?:Private\s+Bag[\s–-]*)?([0-9]+)?"
    r"\s*[-–—]?\s*([0-9]{4,5})"
    r"|Private\s+Bag\s+([0-9]{4,5})"
    r"|\b([0-9]{3,6})\s*[-–—]\s*([0-9]{5})\b",
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
# Building and street words. A cell full of these is an ADDRESS, whatever
# column it ended up in - "Ngano House, Industrial Area" reached the name
# column and became a prospect.
PLACE = re.compile(
    r"\b(house|building|plaza|towers?|centre|center|court|arcade|mall|complex"
    r"|road|street|avenue|lane|highway|floor|wing|block|estate|area|park"
    r"|premises|opposite|junction|stage|suites?|offices?|annex|godown|shop"
    r"|apartments?|flats?|market|square|close|drive|crescent|hill|gardens?"
    r"|chambers|villa|villas|business\s+park|industrial)\b",
    re.IGNORECASE)

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


# A KENYAN ENTITY NAME ENDS AT ITS LEGAL SUFFIX (ruling 2026-08-11: "it will
# be reasonable to say a proper business name ends with LTD in Kenya unless
# otherwise"). Anything after it came from the next column:
#
#     "Jitegemee Sacco Society Ltd Kaunda Street, Mvita, Mombasa"
#      ......................... |  <- everything past here is an address
#
# Cutting at the LAST suffix, not the first, because "Sacco Society Ltd" has
# three and the name runs to the end of them.
LEGAL_END = re.compile(
    r"\b(ltd|limited|plc|llp|llc|inc|incorporated|sacco|society|societies"
    r"|co-?operative|co-?op|company|trust|foundation|association|union"
    r"|scheme|bank|group|holdings|enterprises|agencies|investments)\b\.?",
    re.IGNORECASE)


def trim_to_legal_name(name: str) -> str:
    """Cut a name at its last legal suffix. Unchanged if there is none - plenty
    of real businesses trade without one, and truncating those would do more
    damage than the bleed it fixes."""
    n = str(name or "").strip()
    last = None
    for m in LEGAL_END.finditer(n):
        last = m
    if not last:
        return n
    trimmed = n[:last.end()].strip(" .,-–—")
    return trimmed if len(trimmed) >= 4 else n


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
            # 1. Ruled tables, if the document draws lines.
            got = page.extract_tables() or []
            # ONLY TRUST A DETECTED TABLE IF IT FOUND ENOUGH COLUMNS. pdfplumber
            # happily returns a TWO-column read of a five-column register, and
            # taking it short-circuits the word-position path that would have
            # read all five - so address, town and telephone vanished and every
            # row was rejected as having no address.
            widest = max((len(r) for t in got for r in t), default=0)
            if got and widest >= 3:
                for table in got:
                    for row in table:
                        cells = [(c or "").replace("\n", " ").strip() for c in row]
                        if any(cells):
                            out.append(cells)
                continue

            # 2. NO LINES? Rebuild rows from WORD POSITIONS. The SASRA gazette
            # draws no borders, so extract_tables finds nothing and the text
            # fallback flows columns together - which is what produced
            # "Sacco Nairobi 129 PCEA Ruiru Regulated Non-WDT": the tail of one
            # row and the head of another, read straight across the page.
            #
            # Words carry x/y. Group them into visual lines by `top`, then cut
            # each line into cells wherever there is a WIDE HORIZONTAL GAP -
            # which is exactly what a column boundary is when nobody drew one.
            words = page.extract_words() or []
            if not words:
                continue

            # THE PAGE CARRIES TWO TABLES SIDE BY SIDE. Confirmed from the real
            # gazette: the header "Names of the Regulated | Postal Address |
            # Physical Location | County" appears TWICE on one row, and the
            # column x-positions cluster either side of a gap at mid-page.
            #
            # Every earlier version glued the left table's row to the right
            # table's row, which is where "Sacco Nairobi 129 PCEA Ruiru
            # Regulated Non-WDT" came from - the tail of one entry and the head
            # of another, read straight across. Splitting the page first is the
            # whole fix.
            mid = float(page.width) / 2.0
            # ONLY SPLIT IF THE PAGE REALLY IS TWO-UP. SASRA prints two tables
            # side by side with a clear gutter down the middle; RBA prints one
            # table across the page. Splitting the RBA page cut every row in
            # half - name on the left, address and telephone on the right - so
            # every entry was rejected for having no address.
            #
            # The test is the GUTTER: a two-up page has a band at mid-page that
            # almost no word occupies, because that is the space between the
            # tables. A single wide table has words running straight through it.
            # The test is the REPEATED HEADER. A two-up page prints its column
            # headings twice on one visual line ("... County Names of the
            # Regulated ..."), because there are two tables. A single wide
            # table prints them once. A gutter test was tried first and
            # misfired both ways - a single table can have a column boundary
            # at mid-page, and a two-up page can have a heading that spans it.
            two_up = False
            _lines = {}
            for w in words:
                _lines.setdefault(round(float(w["top"]) / 3.0), []).append(w)
            for _ws in _lines.values():
                txt = " ".join(x["text"] for x in
                               sorted(_ws, key=lambda z: float(z["x0"]))).lower()
                for hdr in ("postal", "county", "physical", "address"):
                    if txt.count(hdr) >= 2:
                        two_up = True
                        break
                if two_up:
                    break
            halves = ([[w for w in words if float(w["x0"]) < mid],
                       [w for w in words if float(w["x0"]) >= mid]]
                      if two_up else [words])

            for half in halves:
                if not half:
                    continue
                lines = {}
                for w in half:
                    lines.setdefault(round(float(w["top"]) / 3.0), []).append(w)

                rows_here = []
                for key in sorted(lines):
                    ws = sorted(lines[key], key=lambda x: float(x["x0"]))
                    cells, cur, prev_end, cell_x = [], [], None, None
                    for w in ws:
                        x0, x1 = float(w["x0"]), float(w["x1"])
                        if prev_end is not None and (x0 - prev_end) > 11:
                            cells.append((" ".join(cur), cell_x))
                            cur, cell_x = [], None
                        if cell_x is None:
                            cell_x = x0
                        cur.append(w["text"])
                        prev_end = x1
                    if cur:
                        cells.append((" ".join(cur), cell_x))
                    cells = [(c.strip(), x) for c, x in cells if c.strip()]
                    if cells:
                        rows_here.append(cells)

                # NAMES WRAP. "17 Banki Kuu Regulated Non-WDT-" is followed by a
                # line reading only "Sacco". A row that does NOT start with an
                # index number is a continuation of the one above, and dropping
                # it truncates the society's name.
                # CALIBRATE COLUMNS FROM THE HEADER, not by guessing per row.
                # "the first cell that is not a number or an address" picked up
                # a LOCATION whenever the name column was empty or merged - so
                # 25 prospects arrived named after a town. The header row says
                # where each column starts; every data cell then belongs to the
                # column it starts nearest to.
                header_x = {}
                for cells in rows_here:
                    joined = " ".join(c for c, _x in cells).lower()
                    # The header row is recognised by ANY address word plus a
                    # name or a place word - SASRA writes "Postal Address",
                    # RBA writes "ADDRESS", and requiring "postal" meant the
                    # RBA header was never found at all.
                    if (("postal" in joined or "address" in joined)
                            and ("name" in joined or "county" in joined
                                 or "town" in joined or "city" in joined)):
                        for c, x in cells:
                            cl = c.lower()
                            if "name" in cl:
                                header_x.setdefault("name", x)
                            elif "postal" in cl or cl.strip() == "address":
                                header_x.setdefault("postal", x)
                            elif "physical" in cl or "location" in cl:
                                header_x.setdefault("physical", x)
                            elif "county" in cl or "town" in cl or "city" in cl:
                                header_x.setdefault("county", x)
                            # RBA publishes TEL and EMAIL columns. Reading them
                            # is worth more than everything else here: a
                            # prospect with a phone and an email starts two
                            # fields higher on the completeness matrix.
                            elif "tel" in cl or "phone" in cl or "mobile" in cl:
                                header_x.setdefault("phone", x)
                            elif "mail" in cl:
                                header_x.setdefault("email", x)
                        break

                # THE HEADER IS NOT ALWAYS FOUND ON BOTH HALVES. The half that
                # missed it fell back to guessing "the first cell that is not a
                # number or an address" - which picked up a PHYSICAL LOCATION.
                # Calibrate from the data instead: cell x-starts cluster into
                # columns, because that is what a column is.
                if not header_x:
                    import collections as _c
                    tally = _c.Counter()
                    for cells in rows_here:
                        for _t, x in cells:
                            tally[round(x / 8.0) * 8] += 1
                    busy = sorted(x for x, n in tally.items() if n >= 3)
                    if len(busy) >= 5:
                        busy = busy[1:]          # drop the index column
                    if len(busy) >= 4:
                        for field, x in zip(("name", "postal", "physical",
                                             "county", "phone", "email"), busy[:6]):
                            header_x[field] = x

                merged = []
                for cells in rows_here:
                    starts_entry = bool(re.match(r"^\d{1,3}$", cells[0][0]))
                    # A continuation is a SINGLE cell with no digits in it.
                    # "<= 2 cells" was too loose and swallowed whole entries -
                    # "153 Total Regulated..." was appended to the previous
                    # society's name.
                    is_tail = (not starts_entry and len(cells) == 1
                               and not any(ch.isdigit() for ch in cells[0][0]))
                    if is_tail and merged and len(merged[-1]) > 1:
                        # KEEP THE HYPHEN: "Non-WDT-" + "Sacco" is
                        # "Non-WDT-Sacco". Stripping it produced "Non-WDTSacco".
                        prev_txt, prev_x = merged[-1][1]
                        joined = (prev_txt + cells[0][0]).strip() \
                            if prev_txt.endswith("-") \
                            else (prev_txt + " " + cells[0][0]).strip()
                        merged[-1][1] = (joined, prev_x)
                        continue
                    merged.append(list(cells))

                # Map each row onto named columns using the header positions.
                for cells in merged:
                    if header_x.get("name") is None:
                        out.append([c for c, _x in cells])
                        continue
                    slot = {}
                    for c, x in cells:
                        best, bestd = None, 1e9
                        for field, hx in header_x.items():
                            d = abs(x - hx)
                            if d < bestd:
                                best, bestd = field, d
                        # A cell far from every header is an index number or
                        # stray mark; drop it rather than let it become a name.
                        if best and bestd <= 60:
                            slot[best] = (slot.get(best, "") + " " + c).strip()
                    out.append(["", slot.get("name", ""), slot.get("postal", ""),
                                slot.get("physical", ""), slot.get("county", ""),
                                slot.get("phone", ""), slot.get("email", "")])
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
            # RBA prints its row number twice and the PDF glues the second copy
            # to the name: "1Amana Personal Pension Plan", "3Benefits At Work".
            # Strip leading digits when a CAPITAL follows immediately - a real
            # name starting with a digit ("2NK Sacco") has no capital glued to
            # it in that way, so it survives.
            name = re.sub(r"^\d{1,3}(?=[A-Z][a-z])", "", name)
            # The same doubling can land at the END: "Fahari Retirement Plan 5".
            name = re.sub(r"\s+\d{1,2}$", "", name)
            name = trim_to_legal_name(name)
            # The header row repeats on every page of a gazette and reads like
            # an entity ("Names of the Deposit Taking SACCO Society" contains
            # both "sacco" and "society"), so it must be dropped explicitly.
            if NOISE.search(name):
                continue
            # A PLACE IS NOT A BUSINESS. "Ngano House, Industrial Area" is a
            # physical-location cell that reached the name column. A society
            # whose real name contains "House" or "Plaza" still carries an
            # entity marker, so it stays.
            if PLACE.search(name) and not any(
                    mk in name.lower() for mk in ENTITY_MARKERS):
                rejected.append((name[:56], "a place, not a business"))
                continue
            # A BARE COUNTY NAME IS NOT A BUSINESS. "Mombasa" carries no place
            # word and reads as a short proper-noun phrase, so every other rule
            # waves it through - it is the county column having landed in the
            # name column.
            if name.strip().lower() in {c.lower() for c in counties}:
                rejected.append((name[:56], "a county name, not a business"))
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
            # Take ONLY the postal address, not whatever the physical-location
            # column merged into the same cell. The box pattern knows where it
            # ends; everything after it belongs to another column.
            # The box pattern knows exactly where it ends. Everything after it
            # belongs to another column, so take the box and append the county
            # we already resolved - rather than guessing where the town ends,
            # which fails when two columns touch ("NairobiCentral Bank").
            addr = ""
            for c in cells:
                mb = BOX.search(c)
                if mb:
                    addr = c[:mb.end()].strip(" ,.-")
                    break
            # A REGISTER ENTRY ALWAYS HAS A POSTAL ADDRESS. That is the column
            # the register exists to publish, and it is the one thing page
            # furniture never has.
            #
            # This is what let SASRA'S OWN LETTERHEAD through as prospects -
            # "THE SACCO SOCIETIES REGULATORY", "Old Mutual Tower", "19th
            # Floor", "Upper Hill Road", "Nairobi, Kenya". Every one reads like
            # a plausible name; not one has a P.O Box.
            if not addr:
                rejected.append((name[:56], "no postal address - not an entry"))
                continue
            key = name.lower()
            if key in seen:
                continue
            seen.add(key)
            rows.append({
                "company_name": name,
                "industry_description": ("%s - %s" % (label, sector)) if label else sector,
                "physical_address": (addr + (", " + town if town else "")).strip(" ,"),
                "town": town,
                "registration_number": "",
                # Straight from the register where it publishes them.
                "company_phone": (cells[5] if len(cells) > 5 else ""),
                "company_email": (cells[6] if len(cells) > 6 else ""),
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
            # RBA prints its row number twice and the PDF glues the second copy
            # to the name: "1Amana Personal Pension Plan", "3Benefits At Work".
            # Strip leading digits when a CAPITAL follows immediately - a real
            # name starting with a digit ("2NK Sacco") has no capital glued to
            # it in that way, so it survives.
            name = re.sub(r"^\d{1,3}(?=[A-Z][a-z])", "", name)
            # The same doubling can land at the END: "Fahari Retirement Plan 5".
            name = re.sub(r"\s+\d{1,2}$", "", name)
            name = trim_to_legal_name(name)
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

    # LABELLED, so every field can be checked rather than inferred from a
    # column of names. Three extractions looked plausible in a name-only
    # sample and were wrong in the fields beside it.
    print("\n  SAMPLE - check EVERY field, not just the name")
    for r in rows[:6]:
        print("     Name     : %s" % r["company_name"][:64])
        print("     Location : %s" % (r["town"] or "(none)"))
        print("     Address  : %s" % (r["physical_address"][:64] or "(none)"))
        print("     Contact  : %s" % (r["company_phone"] or "(none in this register)"))
        print("")

    # A SANITY GATE. Three times now a wrong extraction has reached the shelf
    # looking plausible, because column fragments contain the same words real
    # names do. These checks catch a bad run BEFORE it is imported.
    import statistics
    problems = []
    lens = [len(r["company_name"]) for r in rows]
    if lens and statistics.mean(lens) > 48:
        problems.append("names average %.0f characters - real society names are"
                        " shorter; this looks like column fragments"
                        % statistics.mean(lens))
    # A fragment usually carries a stray index number from the next row.
    with_digits = sum(1 for r in rows if re.search(r"\b\d{2,3}\b", r["company_name"]))
    if rows and with_digits > len(rows) * 0.15:
        problems.append("%d of %d names contain a stray row number - the "
                        "columns are being read across" % (with_digits, len(rows)))
    notown2 = sum(1 for r in rows if not r["town"])
    if rows and notown2 > len(rows) * 0.35:
        problems.append("%d of %d have no county - the county column is not "
                        "being found" % (notown2, len(rows)))
    if problems:
        print("\n" + "!" * 76)
        print("THIS EXTRACTION LOOKS WRONG:")
        for pr in problems:
            print("   * %s" % pr)
        print("")
        print("The CSV has been written so you can inspect it, but DO NOT")
        print("import it - a shelf of fragments is harder to clean than an")
        print("empty one. Send me the sample above and the mode line.")
        print("!" * 76)

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
            raw_sector = str(r.get(cols.get("sector", "")) or "")
            sector = _sector_for(raw_sector, sectors)
            # "SACCO - Financial Services" carries both: the top-level sector
            # for browsing and the SUBSECTOR that says what kind of thing this
            # actually is. Keeping only the first would put a SACCO and a
            # pension scheme on the same undifferentiated shelf.
            subsector = raw_sector.split("-")[0].strip() if "-" in raw_sector else ""
            town = _town_for(
                " ".join(str(r.get(cols.get(k, "")) or "") for k in ("town", "address")),
                towns)
            rows.append({
                "name": name, "sector": sector, "subsector": subsector, "town": town,
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
                sector=r["sector"], subsector=r.get("subsector", ""), town=r["town"],
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
            print("ABORT: %s not found - apply patch_rb1_second_register.py first." % p)
            return 1

    mod = open(MOD, encoding="utf-8").read()
    if '"subsector"' in mod:
        print("ABORT: subsector already present - LIB1 looks applied.")
        return 1
    if "def shelves(status" not in mod or "def create(*, name: str" not in mod:
        print("ABORT: the store is not in the expected shape.")
        return 1

    i = mod.index("def shelves(status: str = STATUS_AVAILABLE) -> dict:")
    j = mod.index("\ndef ", i + 10)
    k = mod.index("def create(*, name: str")
    l = mod.index("def claim(")
    if k < i:
        mod = mod[:k] + CREATE + mod[l:i] + SHELVES + mod[j:]
    else:
        mod = mod[:i] + SHELVES + mod[j:k] + CREATE + mod[l:]
    print("  ok  subsector, library shelves")

    # Alphabetical, or the ruling is not met.
    if 'r.get("name") or ""' not in SHELVES:
        print("ABORT: shelves are not sorted by name.")
        return 1
    if "dict(sorted(out.items()))" not in SHELVES:
        print("ABORT: the shelves themselves are unordered - the library would")
        print("       rearrange itself as data arrived.")
        return 1
    if "subsector" not in SHELVES or "subsector" not in CREATE:
        print("ABORT: subsector is missing.")
        return 1
    # The digit strip must not eat a real leading digit.
    if "(?=[A-Z][a-z])" not in EXTRACTOR:
        print("ABORT: leading digits are stripped unconditionally - '2NK Sacco")
        print("       Society Ltd' would be mangled.")
        return 1
    if EXTRACTOR.count("name = re.sub(r\"^\\d{1,3}(?=[A-Z][a-z])\", \"\", name)") != 2:
        print("ABORT: the digit strip is not on both extraction paths.")
        return 1
    if "subsector" not in IMPORTER:
        print("ABORT: the importer drops the subsector.")
        return 1
    print("  ok  post-checks: alphabetical, subsectored, digits safe")

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
    print("RE-IMPORT both registers - existing records have no subsector and")
    print("will otherwise stay on the undifferentiated shelf.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
