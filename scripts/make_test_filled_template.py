#!/usr/bin/env python3
"""scripts/make_test_filled_template.py — produce a FILLED test upload
(data/STAFF_UPLOAD_TEST_FILLED.xlsx) with a complete synthetic org tree:
MD -> 10 EXCO/direct reports -> heads -> regional heads -> 16 branch managers
-> branch staff + full DSA chain (with dual lines). For DRY-RUN testing of the
upload pipeline ONLY. Throwaway data.
"""
from pathlib import Path
from openpyxl import Workbook
from utils.core import get_org_config

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "data" / "STAFF_UPLOAD_TEST_FILLED.xlsx"
cfg = get_org_config() or {}
BRANCHES = [b["name"] for b in cfg.get("branches", []) if b.get("type") != "HO"]
DSA_REGIONS = ["Nairobi CBD", "Nairobi Metro", "Coast", "North Rift",
               "South Rift", "West Kenya", "Mt Kenya East", "Mt Kenya West"]

COLS = ["Staff Code", "Staff Name", "Role", "Branch", "Region (DSA only)",
        "Reports To Code", "Dotted Line Code 1", "Dotted Line Code 2",
        "Band", "Gender", "Email", "Date of Employment"]

rows = []
code = [300000]
def nxt():
    code[0] += 1; return str(code[0])

# Root
md = nxt()
rows.append([md, "Test MD", "Managing Director", "Head Office", "", "", "", "", "E1", "M", "", ""])

# 10 reporting to MD: 2 directors + DSA Head (via CCB) + Head of Sales-ish + 6 chiefs/heads
ccb = nxt(); rows.append([ccb, "Test Director CCB", "Director Consumer & Commercial Banking (CCB)", "Head Office", "", md, "", "", "E2", "F", "", ""])
cib = nxt(); rows.append([cib, "Test Director CIB", "Director Corporate & Investment Banking (CIB)", "Head Office", "", md, "", "", "E2", "M", "", ""])
cfo = nxt(); rows.append([cfo, "Test CFO", "Chief Finance Officer", "Head Office", "", md, "", "", "E2", "F", "", ""])
cro = nxt(); rows.append([cro, "Test CRO", "Chief Risk Officer", "Head Office", "", md, "", "", "E2", "M", "", ""])
coo = nxt(); rows.append([coo, "Test COO", "Chief Operations Officer", "Head Office", "", md, "", "", "E2", "F", "", ""])
cco = nxt(); rows.append([cco, "Test CCO", "Chief Compliance Officer", "Head Office", "", md, "", "", "E2", "M", "", ""])
chro = nxt(); rows.append([chro, "Test CHRO", "Chief Human Resources Officer", "Head Office", "", md, "", "", "E2", "F", "", ""])
# under CCB: Head of Retail, DSA Head
hret = nxt(); rows.append([hret, "Test Head Retail", "Head Of Retail", "Head Office", "", ccb, "", "", "E3", "M", "", ""])
dsah = nxt(); rows.append([dsah, "Test DSA Head", "DSA Head", "Head Office", "", ccb, "", "", "E3", "F", "", ""])
# under CIB: Head of Corporate, Head of SME
hcorp = nxt(); rows.append([hcorp, "Test Head Corp", "Head Of Corporate", "Head Office", "", cib, "", "", "E3", "M", "", ""])
hsme = nxt(); rows.append([hsme, "Test Head SME", "Head Of SME", "Head Office", "", cib, "", "", "E3", "F", "", ""])

# Regional Head (one, under Head of Retail) — region-scoped
rh = nxt(); rows.append([rh, "Test Regional Head", "Regional Head", "Head Office", "", hret, "", "", "M1", "M", "", ""])

# Regional DSA Heads (map to a few DSA regions, under DSA Head)
rdsa = {}
for reg in DSA_REGIONS[:4]:
    c = nxt(); rdsa[reg] = c
    rows.append([c, f"Test RDSA {reg}", "Regional DSA Head", "Head Office", reg, dsah, "", "", "M1", "M", "", ""])

# Per branch: Branch Manager -> Ops Mgr (Teller/CSO/BOS) + Credit Mgr (RO PB/RO BB)
#             + Branch DSA Team Lead -> Direct Sales Agent (dual line)
def region_for(i): return DSA_REGIONS[i % 4]
for i, br in enumerate(BRANCHES):
    bm = nxt(); rows.append([bm, f"Test BM {br}", "Branch Manager", br, "", rh, "", "", "M2", "M", "", ""])
    om = nxt(); rows.append([om, f"Test OpsMgr {br}", "Branch Operations Manager", br, "", bm, "", "", "O1", "F", "", ""])
    cm = nxt(); rows.append([cm, f"Test CreditMgr {br}", "Branch Credit Manager", br, "", bm, "", "", "O1", "M", "", ""])
    rows.append([nxt(), f"Test Teller {br}", "Teller", br, "", om, "", "", "O3", "F", "", ""])
    rows.append([nxt(), f"Test CSO {br}", "Customer Service Officer", br, "", om, "", "", "O3", "M", "", ""])
    rows.append([nxt(), f"Test ROPB {br}", "Relationship Officer Personal Banking", br, "", cm, "", "", "O2", "F", "", ""])
    rows.append([nxt(), f"Test ROBB {br}", "Relationship Officer Business Banking", br, "", cm, "", "", "O2", "M", "", ""])
    # DSA chain: Team Lead -> DSA (primary=BM, dotted=[TL, RDSA])
    reg = region_for(i)
    tl = nxt(); rows.append([tl, f"Test DSATL {br}", "Branch DSA Team Lead", br, reg, rdsa.get(reg, dsah), "", "", "O2", "M", "", ""])
    rows.append([nxt(), f"Test DSA1 {br}", "Direct Sales Agent", br, reg, bm, tl, rdsa.get(reg, ""), "O3", "F", "", ""])
    rows.append([nxt(), f"Test DSA2 {br}", "Direct Sales Agent", br, reg, bm, tl, rdsa.get(reg, ""), "O3", "M", "", ""])

wb = Workbook(); ws = wb.active; ws.title = "Staff"; ws.append(COLS)
for r in rows: ws.append(r)
wb.save(OUT)
print(f"  wrote {OUT.relative_to(ROOT)} with {len(rows)} staff rows")
print(f"  branches: {len(BRANCHES)} | reporting to MD directly: ", sum(1 for r in rows if r[5]==md))
