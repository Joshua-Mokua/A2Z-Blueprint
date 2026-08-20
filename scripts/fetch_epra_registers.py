#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
Take all 31 EPRA licensee registers in one pass. DRY RUN by default.

EPRA publishes petroleum licensing as 31 separate registers on one portal -
LPG import, wholesale, retail, autogas, lubricants, bitumen, jet fuel,
transport by road, rail and pipeline. Same table on every page.

Doing them one at a time is 93 commands and a slug typed wrong somewhere.

    python scripts\\fetch_epra_registers.py
    python scripts\\fetch_epra_registers.py --apply

IT IS POLITE. One page at a time, a pause between, and it stops on the first
refusal rather than hammering a government server that has already been
generous in publishing this at all.

Downloads to data\\registers\\epra\\ so the sources are kept, then writes one
CSV per register. The import is left to you - so you see what came out before
40,000 records land on the shelf.
"""
import os
import subprocess
import sys
import time
import urllib.request

BASE = "https://portal.epra.go.ke:8450/licence-register/"
OUT = os.path.join("data", "registers", "epra")

# slug -> what it is, in words an officer would recognise
REGISTERS = [
    ("export-wholesale-lpg-bulk", "LPG export and wholesale, bulk"),
    ("import-export-wholesale-lpg-bulk", "LPG import, export and wholesale, bulk"),
    ("storage-lpg-bulk", "LPG storage, bulk"),
    ("storage-filling-lpg-bulk", "LPG storage and filling, bulk"),
    ("storage-filling-lpg-cylinders", "LPG storage and filling, cylinders"),
    ("storage-wholesale-lpg-cylinders", "LPG storage and wholesale, cylinders"),
    ("retail-lpg-cylinders", "LPG retail, cylinders"),
    ("retail-lpg-cylinders-smart-meters", "LPG retail, smart meters"),
    ("retail-lpg-autogas-dispensing-station", "LPG retail, autogas station"),
    ("reticulation-lpg", "LPG reticulation"),
    ("transport-lpg-cylinders", "LPG transport, cylinders"),
    ("transport-lpg-cylinders-bulk-by-road", "LPG transport, bulk by road"),
    ("retail-petroleum-products-except-lpg", "Petroleum retail"),
    ("export-wholesale-petroleum-products-except-lpg", "Petroleum export and wholesale"),
    ("import-export-wholesale-petroleum-products-except-lpg",
     "Petroleum import, export and wholesale"),
    ("storage-petroleum-products-except-lpg", "Petroleum storage"),
    ("transport-petroleum-products-except-lpg-by-road", "Petroleum transport by road"),
    ("transport-by-railway-petroleum-products-except-lpg", "Petroleum transport by rail"),
    ("transport-petroleum-products-via-pipeline", "Petroleum transport by pipeline"),
    ("bunkering-petroleum-products-except-lpg", "Petroleum bunkering"),
    ("export-wholesale-crude-oil", "Crude oil export and wholesale"),
    ("storage-crude-oil", "Crude oil storage"),
    ("export-wholesale-jet-a1", "Jet A1 export and wholesale"),
    ("transport-jet-a1", "Jet A1 transport"),
    ("import-lubricants", "Lubricants import"),
    ("export-wholesale-of-lubricants", "Lubricants export and wholesale"),
    ("blending-of-lubricants", "Lubricants blending"),
    ("bulk-storage-of-lubricants", "Lubricants storage, bulk"),
    ("import-export-wholesale-bitumen", "Bitumen import, export and wholesale"),
    ("import-export-wholesale-fuel-oil", "Fuel oil import, export and wholesale"),
]

PAUSE = 2.0


def main():
    apply = "--apply" in sys.argv
    print("=" * 76)
    print("EPRA LICENSEE REGISTERS")
    print("=" * 76)
    print("  registers   %d" % len(REGISTERS))
    print("  saved to    %s" % OUT)
    print("  pause       %.0fs between pages" % PAUSE)
    print("\n  A government server publishing this at all is doing us a")
    print("  favour. One page at a time, and it stops on the first refusal.")
    if not apply:
        print("\n  WILL FETCH:")
        for slug, what in REGISTERS[:8]:
            print("     %-52s %s" % (slug[:52], what))
        print("     ... and %d more" % (len(REGISTERS) - 8))
        print("\nDRY RUN - nothing fetched. Re-run with --apply.")
        return 0

    os.makedirs(OUT, exist_ok=True)
    got, failed, rows_total = 0, [], 0
    for n, (slug, what) in enumerate(REGISTERS, start=1):
        dest = os.path.join(OUT, "epra_%s.html" % slug.replace("-", "_"))
        print("\n[%2d/%d] %s" % (n, len(REGISTERS), what))
        try:
            req = urllib.request.Request(
                BASE + slug,
                headers={"User-Agent": "Mozilla/5.0 (A2Z warehouse import)"})
            with urllib.request.urlopen(req, timeout=60) as r:
                html = r.read().decode("utf-8", "ignore")
            open(dest, "w", encoding="utf-8").write(html)
            got += 1
        except Exception as exc:
            print("     FAILED: %s" % str(exc)[:60])
            failed.append((slug, str(exc)[:40]))
            if len(failed) >= 3:
                print("\n  Three refusals in a row. STOPPING - the server is")
                print("  saying no and it should not be argued with.")
                break
            time.sleep(PAUSE * 2)
            continue

        r = subprocess.run(
            [sys.executable, os.path.join("scripts", "extract_html_register.py"),
             dest, "--label", what, "--sector", "Energy & Petroleum"],
            capture_output=True, text=True)
        for line in r.stdout.split("\n"):
            if "EXTRACTED" in line or "skipped" in line:
                print("     %s" % line.strip())
            if "EXTRACTED" in line:
                try:
                    rows_total += int(line.split()[-1])
                except ValueError:
                    pass
        time.sleep(PAUSE)

    print("\n" + "=" * 76)
    print("  fetched     %d of %d" % (got, len(REGISTERS)))
    print("  rows read   %d" % rows_total)
    if failed:
        print("  failed      %d" % len(failed))
        for slug, why in failed:
            print("     %-46s %s" % (slug[:46], why))
    print("\n  The CSVs are beside this script. Import the ones you want:")
    print("     python scripts\\import_business_register.py epra_<name>.csv \\")
    print("         --apply --source \"EPRA licensee register - <what>\" \\")
    print("         --licence \"published register\"")
    print("\n  Nothing has been imported. Look at a CSV or two first - 31")
    print("  registers is a lot to put on the shelf unseen.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
