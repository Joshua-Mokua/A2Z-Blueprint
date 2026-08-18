"""
diag_tat_switch.py  (v2) — READ-ONLY dry-run for S4a (no mutation).

v2 fix: reads LIVE data through the project loaders (get_kpi_library,
LoanApplicationManager, _load_status_vocabulary) and the actuals engine —
NOT by reading data/*.json directly (which can be stale/empty/DB-backed).

Shows, on YOUR live data:
  A. Engine's authoritative K011 today (current rule) + sample.
  B. OLD K011 = mean(last_updated - application_date)  vs
     NEW K011 = mean(tat_days)   over decided loan_applications.
  C. TAT KPIs in the live library (K011 vs CREDIT_TAT dedup question).
  D. Which roles assign a TAT KPI + weight (score-impact map).

Run from project root with venv active:
    .venv\\Scripts\\activate
    python scripts\\diag_tat_switch.py            (period 2026-02)
    python scripts\\diag_tat_switch.py 2026-02
"""
from __future__ import annotations
import sys, json, pathlib
from datetime import date
from statistics import mean
from collections import defaultdict, Counter

PERIOD = sys.argv[1] if len(sys.argv) > 1 else "2026-02"
ROOT = pathlib.Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))

def hdr(t): print("\n" + "=" * 72 + f"\n{t}\n" + "=" * 72)
def _d(x):
    try: return date.fromisoformat(str(x)[:10])
    except Exception: return None
def _m(v): return round(mean(v), 1) if v else None

# ── live loaders ─────────────────────────────────────────────────────────
try:
    from utils.core import get_kpi_library, LoanApplicationManager, DATA_DIR
    print(f"[ok] DATA_DIR = {DATA_DIR}")
except Exception as e:
    print(f"[FATAL] cannot import utils.core: {e}"); sys.exit(1)

apps = []
try:
    apps = LoanApplicationManager().apps or []
except Exception as e:
    print(f"[warn] LoanApplicationManager: {e}")
print(f"[ok] loan_applications via manager: {len(apps)} rows")

# decided vocab
decided = set()
try:
    from utils.aggregation_rules_loader import _load_status_vocabulary
    vocab = _load_status_vocabulary()
    decided = set(vocab.get("loan_decided") or [])
    print(f"[ok] loan_decided vocab: {sorted(decided)}")
except Exception as e:
    print(f"[warn] vocab load failed: {e}")
if not decided:
    decided = {"approved", "disbursed", "declined", "returned"}
    print(f"[note] fallback loan_decided = {sorted(decided)}")

# ── A. engine authoritative K011 ─────────────────────────────────────────
hdr(f"A. ENGINE K011 TODAY  (current rule, period {PERIOD})")
try:
    from utils.actuals_engine import compute_actuals_from_operational_tables as _eng
    res = _eng(PERIOD)
    samples = res.get("samples") or res.get("preview") or []
    k011 = [s for s in samples if str(s.get("kpi_id")) == "K011"][:5]
    print(f"  rules_applied={res.get('rules_applied')}  actuals_submitted={res.get('actuals_submitted')}")
    if k011:
        for s in k011:
            print(f"    K011 sample: staff={s.get('staff_code')} actual={s.get('actual')}")
    else:
        print("  (no K011 in samples — engine may summarize differently; see counts above)")
except Exception as e:
    print(f"  [warn] engine call failed: {e}")

# ── B. OLD vs NEW over decided apps ──────────────────────────────────────
hdr("B. OLD (calendar) vs NEW (tat_days)  — decided loan_applications")
if not apps:
    print("  loan_applications manager returned 0 rows.")
    print("  -> If engine K011 above HAS values, the engine reads from the DB, not this JSON;")
    print("     the S4a backfill must then target the DB rows. Tell me which and I'll adjust.")
else:
    print(f"  statuses present: {dict(Counter(str(a.get('status')) for a in apps))}")
    old_v, new_v = [], []
    p_old, p_new = defaultdict(list), defaultdict(list)
    nd = 0
    for a in apps:
        if str(a.get("status")) not in decided: continue
        nd += 1
        rm = a.get("rm_code") or a.get("rm_name") or "?"
        sd, ed = _d(a.get("application_date")), _d(a.get("last_updated"))
        if sd and ed and ed >= sd:
            old_v.append((ed - sd).days); p_old[rm].append((ed - sd).days)
        td = a.get("tat_days")
        if isinstance(td, (int, float)):
            new_v.append(td); p_new[rm].append(td)
    print(f"  decided rows: {nd}")
    print(f"  OLD mean TAT (calendar app->last_updated): {_m(old_v)}  (n={len(old_v)})")
    print(f"  NEW mean TAT (tat_days field)            : {_m(new_v)}  (n={len(new_v)})")
    if _m(old_v) and _m(new_v):
        print(f"  delta: {round(_m(new_v)-_m(old_v),1)} days")
    top = sorted(p_new, key=lambda k: -len(p_new[k]))[:8]
    if top:
        print("  Per-RM (top 8):  RM   OLD -> NEW")
        for rm in top:
            print(f"    {str(rm):<12} {str(_m(p_old.get(rm,[]))):>6} -> {str(_m(p_new.get(rm,[]))):>6}  (n={len(p_new[rm])})")

# ── C. library dedup ─────────────────────────────────────────────────────
hdr("C. TAT KPIs in LIVE library  (K011 vs CREDIT_TAT)")
lib = {}
try:
    lib = get_kpi_library() or {}
except Exception as e:
    print(f"  [warn] get_kpi_library failed: {e}")
def _walk(obj, out):
    if isinstance(obj, dict):
        if (obj.get("id") or obj.get("name")) and ("direction" in obj or "pillar" in obj or "weight" in obj):
            out.append(obj)
        for v in obj.values(): _walk(v, out)
    elif isinstance(obj, list):
        for v in obj: _walk(v, out)
kpis = []
_walk(lib, kpis)
print(f"  library KPI-like entries found: {len(kpis)}")
tat = [k for k in kpis if any(w in json.dumps(k).lower() for w in ("tat","turnaround","approval","processing"))]
for k in tat:
    print(f"    {str(k.get('id') or '?'):<12} {str(k.get('name') or '?'):<34} "
          f"dir={str(k.get('direction') or '?'):<6} src={str(k.get('source') or '?'):<18} "
          f"w={k.get('weight')} aliases={k.get('aliases')}")
if not tat:
    print("  (no TAT KPI in displayed library — may be registry-only / code-canonical)")

# ── D. role assignment / score impact ────────────────────────────────────
hdr("D. ROLE assignment of TAT KPI  (does the switch move scores?)")
found = False
try:
    from compute_actuals import ROLE_KPI_WEIGHTS
    for role, w in ROLE_KPI_WEIGHTS.items():
        for k, wt in w.items():
            if any(x in str(k).lower() for x in ("tat","turnaround","approval")):
                print(f"  [ROLE_KPI_WEIGHTS] {role}: {k} = {wt}"); found = True
except Exception as e:
    print(f"  [note] ROLE_KPI_WEIGHTS: {e}")
rk = lib.get("role_kpis") if isinstance(lib, dict) else None
if isinstance(rk, dict):
    for role, ids in rk.items():
        flat = ids if isinstance(ids, (list, tuple)) else (list(ids) if hasattr(ids,'__iter__') and not isinstance(ids,str) else [ids])
        hits = [i for i in flat if str(i) in ("K011","K061","CREDIT_TAT") or "tat" in str(i).lower() or "approval" in str(i).lower()]
        if hits:
            print(f"  [library role_kpis] {role}: {hits}"); found = True
if not found:
    print("  No TAT KPI in any readable role map -> switch is SCORE-SAFE here.")
    print("  (Confirm against your live role config; if truly unweighted, no appraisal moves.)")
print()
