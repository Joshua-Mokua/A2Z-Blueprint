"""
diag_bsc_tat.py — READ-ONLY BSC diagnostic (no server, no mutations).

Confirms, on Josh's LIVE data, the items S4 will touch:
  1. TAT KPI overlap  — manual "Credit Approval TAT" vs auto "TAT Loan Processing"
  2. TAT populated?   — does the auto TAT engine return a value or None this period?
  3. Disbursement->BSC— are disbursed credit cases reflected in K001's source (loans_master)?
  4. Generic registry — is kpi_aggregation_rules.REGISTRY wired or empty?

Run from project root with the venv active:
    .venv\\Scripts\\activate
    python scripts\\diag_bsc_tat.py            (defaults to period 2026-02)
    python scripts\\diag_bsc_tat.py 2026-02

Pure read. Reports PASS / FLAG / INFO per check, then a verdict block.
"""
from __future__ import annotations
import sys, json, pathlib, inspect

PERIOD = sys.argv[1] if len(sys.argv) > 1 else "2026-02"
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def hdr(t): print("\n" + "=" * 72 + f"\n{t}\n" + "=" * 72)
def line(tag, msg): print(f"  [{tag}] {msg}")

findings = []  # (severity, text)

# ── 0. Locate the LIVE KPI library ───────────────────────────────────────
hdr("0. KPI LIBRARY")
lib_items = []
lib_path = None
for cand in ("a2z/data/kpi_library.json", "data/kpi_library.json"):
    p = ROOT / cand
    if p.exists():
        try:
            raw = json.loads(p.read_text(encoding="utf-8"))
            items = raw if isinstance(raw, list) else list(raw.values())
            if len(items) > len(lib_items):
                lib_items, lib_path = items, cand
        except Exception as e:
            line("WARN", f"{cand}: parse error {e}")
if lib_items:
    line("INFO", f"library: {lib_path}  ({len(lib_items)} KPIs)")
else:
    line("WARN", "no kpi_library.json found — library checks skipped")

# ── 1. TAT KPI overlap ───────────────────────────────────────────────────
hdr("1. TAT KPI OVERLAP  (manual vs auto)")
def _is_tat(it):
    s = (str(it.get("name","")) + " " + str(it.get("id",""))).lower()
    return any(w in s for w in ("tat", "turnaround", "approval", "processing"))
tat_kpis = [it for it in lib_items if isinstance(it, dict) and _is_tat(it)]
if not tat_kpis:
    line("INFO", "no TAT-like KPIs in library (may be code-canonical only)")
for it in tat_kpis:
    line("INFO", f"{it.get('id'):<8} {it.get('name','?'):<34} "
                 f"dir={it.get('direction','?'):<6} src={it.get('source','?'):<22} "
                 f"w={it.get('weight','?')}")
manual_tat = [it for it in tat_kpis if str(it.get("source","")).lower() in ("manual","")]
auto_tat   = [it for it in tat_kpis if str(it.get("source","")).lower() not in ("manual","")]
if manual_tat and auto_tat:
    findings.append(("FLAG",
        f"TAT overlap: {len(manual_tat)} manual + {len(auto_tat)} auto TAT KPIs — "
        "possible dedup target (S4 should consolidate, not add a 3rd)."))
    line("FLAG", "manual AND auto TAT KPIs both present — see verdict")
else:
    line("PASS", "no manual/auto TAT split detected in library")

# also surface the credit engine's declared TAT sources
try:
    from utils.credit_actuals_engine import CREDIT_KPI_SOURCES
    eng_tat = {k: v for k, v in CREDIT_KPI_SOURCES.items()
               if any(w in v.get("name","").lower() for w in ("tat","turnaround","processing"))}
    line("INFO", "credit_actuals_engine TAT sources:")
    for k, v in eng_tat.items():
        line("INFO", f"   {k}: {v.get('name')}  <- {v.get('source')}")
except Exception as e:
    line("WARN", f"could not import CREDIT_KPI_SOURCES: {e}")

# ── 2. Is the auto TAT actually populated this period? ───────────────────
hdr(f"2. AUTO TAT POPULATED?  (period {PERIOD})")
def _call_bankwide(fn, kpi):
    """Call compute_bank_wide_credit_kpi defensively across arg orders."""
    try:
        sig = inspect.signature(fn)
        params = list(sig.parameters)
        if "period" in params:
            return fn(kpi, PERIOD)
        return fn(kpi)
    except TypeError:
        try: return fn(kpi, PERIOD)
        except Exception as e: return f"<err {e}>"
    except Exception as e:
        return f"<err {e}>"
try:
    from utils.credit_actuals_engine import compute_bank_wide_credit_kpi as _bw
    for kpi in ("K011", "K061"):
        val = _call_bankwide(_bw, kpi)
        if val is None:
            findings.append(("FLAG", f"{kpi}: auto TAT returned None — source log likely empty/unpopulated."))
            line("FLAG", f"{kpi}: None (not populated)")
        elif isinstance(val, str) and val.startswith("<err"):
            line("WARN", f"{kpi}: {val}")
        else:
            line("PASS", f"{kpi}: {val}")
except Exception as e:
    line("WARN", f"compute_bank_wide_credit_kpi unavailable: {e}")

# source log presence (credit_workflow_log.json) — the K011 tributary
try:
    from utils.credit_actuals_engine import DATA_DIR as _DD
    wlog = pathlib.Path(_DD) / "credit_workflow_log.json"
except Exception:
    wlog = None
    for cand in ("a2z/data/credit_workflow_log.json", "data/credit_workflow_log.json"):
        if (ROOT / cand).exists(): wlog = ROOT / cand; break
if wlog and pathlib.Path(wlog).exists():
    try:
        wl = json.loads(pathlib.Path(wlog).read_text(encoding="utf-8"))
        n = len(wl) if hasattr(wl, "__len__") else "?"
        line("INFO", f"credit_workflow_log.json present — {n} entries")
        if n == 0:
            findings.append(("FLAG", "credit_workflow_log.json is EMPTY — K011 has no tributary data."))
    except Exception as e:
        line("WARN", f"workflow log parse error: {e}")
else:
    findings.append(("FLAG", "credit_workflow_log.json NOT found — K011 source missing; "
                             "our SLA step-stamps are the natural replacement tributary."))
    line("FLAG", "credit_workflow_log.json not found")

# ── 3. Disbursement -> BSC (K001) gap ────────────────────────────────────
hdr("3. DISBURSEMENT -> BSC  (does disburse reach K001's source?)")
disbursed = None
try:
    from utils.core import CreditAdminManager
    cm = CreditAdminManager()
    cases = cm.cases
    case_list = list(cases.values()) if isinstance(cases, dict) else list(cases)
    disbursed = sum(1 for c in case_list
                    if (c.get("disbursed") is True if isinstance(c, dict) else getattr(c, "disbursed", False)))
    line("INFO", f"credit_admin cases: {len(case_list)}  |  disbursed=True: {disbursed}")
except Exception as e:
    line("WARN", f"CreditAdminManager unavailable: {e}")

# loans_master row count (fast metadata read, no full load)
lm = None
for cand in ("cbs_data/loans_master.parquet", "a2z/cbs_data/loans_master.parquet"):
    if (ROOT / cand).exists(): lm = ROOT / cand; break
if lm:
    try:
        import pyarrow.parquet as pq
        nrows = pq.ParquetFile(str(lm)).metadata.num_rows
        line("INFO", f"loans_master.parquet present — {nrows:,} rows")
    except Exception as e:
        line("WARN", f"could not read parquet metadata: {e}")
else:
    line("WARN", "loans_master.parquet not found at expected paths")

if disbursed:
    findings.append(("FLAG",
        f"{disbursed} disbursed case(s) exist, but NO code path writes disbursed loans into "
        "loans_master (K001's source). So flow-disbursed loans likely do NOT autopopulate K001. "
        "Confirm by checking whether these disbursements appear in the loan book actual."))
    line("FLAG", "disbursed cases exist but no writer into loans_master found (grep-confirmed)")
else:
    line("INFO", "no disbursed cases to test the autopopulate path against")

# ── 4. Generic operational registry ──────────────────────────────────────
hdr("4. GENERIC OPERATIONAL REGISTRY")
try:
    from utils.kpi_aggregation_rules import REGISTRY
    n = len(REGISTRY)
    if n == 0:
        findings.append(("INFO", "kpi_aggregation_rules.REGISTRY is EMPTY — second tributary inactive "
                                 "(not a violation; it's the seam S4 can use)."))
        line("INFO", "REGISTRY is empty (0 rules) — available seam for the SLA-TAT rule")
    else:
        line("PASS", f"REGISTRY has {n} rule(s)")
        for r in REGISTRY:
            line("INFO", f"   {getattr(r,'kpi_id','?')} <- {getattr(r,'source_table','?')} "
                         f"[{getattr(r,'pattern','?')}]")
except Exception as e:
    line("WARN", f"REGISTRY unavailable: {e}")

# ── VERDICT ──────────────────────────────────────────────────────────────
hdr("VERDICT")
flags = [f for f in findings if f[0] == "FLAG"]
infos = [f for f in findings if f[0] == "INFO"]
if not flags:
    print("  CLEAN — no blocking BSC violations on the items S4 will touch.")
else:
    print(f"  {len(flags)} item(s) to address before/while wiring S4:")
    for _, t in flags: print(f"    - {t}")
if infos:
    print("\n  Notes:")
    for _, t in infos: print(f"    - {t}")
print()
