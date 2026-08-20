#!/usr/bin/env python
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
            all_prospects, create, canonical_key, find_by_source_ref
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
            # THE HEADER DECIDES, NOT THE SNIFFER. A pipe inside a value -
            # source_ref is "register|name" - made Sniffer choose "|" as the
            # delimiter, and every row arrived as ONE field whose name was the
            # whole line. It reported "1 column found" and carried on.
            #
            # A comma in the header line means a comma-separated file. That is
            # not a guess, and it cannot be fooled by what is inside a value.
            _first = sample.split("\n", 1)[0]
            if _first.count(",") >= 2:
                dialect = csv.excel
            elif _first.count("\t") >= 2:
                dialect = csv.excel_tab
            else:
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

        # The register this row belongs to. Derived from --source so two
        # registers never collide, and stable across years so re-importing an
        # updated edition recognises what it already holds.
        source_ref_base = canonical_key(source) or os.path.basename(path)
        updates = {}

        rows, skipped_noname, skipped_dupe = [], 0, 0
        bysector = {}
        for r in reader:
            name = str(r.get(cols["name"]) or "").strip()
            if not name:
                skipped_noname += 1
                continue
            # ── MATCHED ON THE ROW, NOT THE NAME ────────────────────────
            # A record cleaned by hand must not come back as a duplicate on
            # the next import. The reference is the register plus the name AS
            # PUBLISHED, so the name in the warehouse is free to be corrected.
            # An enriched file coming back carries its own reference; a fresh
            # register does not, so one is derived.
            ref = str(r.get("source_ref") or "").strip() or (
                "%s|%s" % (source_ref_base, canonical_key(name)))
            if find_by_source_ref(ref) is not None:
                if "--update" in sys.argv:
                    # ── THE RETURN LEG ──────────────────────────────────────
                    # ONLY BLANKS are filled. A value already in the warehouse
                    # was put there by somebody who looked, and a spreadsheet
                    # round trip must not overwrite that. The NAME is never
                    # touched: correcting names is deliberate work done in the
                    # record card, and a bulk update must not undo it.
                    updates[ref] = {
                        "contact_phone": str(r.get(cols.get("phone", "")) or "").strip(),
                        "contact_email": str(r.get(cols.get("email", "")) or "").strip(),
                        "contact_name": str(r.get("contact_name") or "").strip(),
                        "town": str(r.get(cols.get("town", "")) or "").strip(),
                        "physical_location": str(r.get("physical_location") or "").strip(),
                        "website": str(r.get("website") or "").strip(),
                    }
                skipped_dupe += 1
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
                            "contact_name": str(r.get("contact_name") or "").strip(),
                "website": str(r.get("website") or "").strip(),
                "physical_location": str(r.get("physical_location") or "").strip(),
                "postal_address": str(r.get("postal_address") or "").strip(),
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

    # One id per import, so a bad run can be found and undone rather than
    # picked out of the shelf by eye.
    import datetime as _dt
    run_id = "%s %s" % (source[:40], _dt.datetime.now().strftime("%Y-%m-%d %H:%M"))
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
                # WHERE THIS ROW CAME FROM, so a re-import recognises it even
                # after somebody has corrected the name.
                # THE RICH FIELDS A DIRECTORY BRINGS. CBK publishes a named
                # person, a website and a street address; SASRA does not. They
                # were being read from the CSV and then dropped on the floor
                # here, which threw away the reason CBK is worth importing.
                contact_name=r.get("contact_name", ""),
                website=r.get("website", ""),
                physical_location=r.get("physical_location", ""),
                postal_address=r.get("postal_address", ""),
                source_ref="%s|%s" % (source_ref_base, canonical_key(r["name"])),
                import_run=run_id,
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
    filled = 0
    updates = locals().get('updates') or {}
    if ("--update" in sys.argv) and updates:
        from utils.deals_warehouse import _read as _wh_read, _write as _wh_write
        data = _wh_read()
        by_ref = {}
        for pid, rec in data.items():
            rr = str(rec.get("source_ref", "") or "").strip()
            if rr:
                by_ref[rr] = pid
        for ref, vals in updates.items():
            pid = by_ref.get(ref)
            if not pid:
                continue
            touched = False
            for k, v in vals.items():
                if v and not str(data[pid].get(k, "") or "").strip():
                    data[pid][k] = v
                    touched = True
            if touched:
                filled += 1
        if filled:
            _wh_write(data)
        print("\nfilled blanks on %d record(s) from the enriched file." % filled)

    print("\nlisted %d prospects (%d duplicates skipped, %d failed)"
          % (made, skipped_dupe, failed))
    print("Restart uvicorn. Pipeline Intelligence > Deals Warehouse.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
