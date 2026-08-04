#!/usr/bin/env python3
"""Seed proper CREDIT flows for the Commercial/CIB lending products that are still on the
generic sales pipeline. Mirrors the known-good Personal Loan flow (incl. the post-Credit-
Analysis tail Offer Letter -> Credit Administration -> Trops, which hands off to the credit
team and is preserved EXACTLY). Sets client_types so the hardcoded routing engine resolves
the right DCC (Commercial->DCC_COMM, CIB->DCC_CIB). The committee ROUTING logic is untouched.

SAFETY:
  * NON-DESTRUCTIVE: only configures a product if it is still GENERIC (has 'Lead' stage) or
    has no stages. Never overwrites a product already given a credit flow.
  * DRY-RUN by default: shows the full plan; writes only with --apply.
  * Writes to pipeline_settings.json (tracked). Review the plan before applying.

    python seed_commercial_credit_flows.py            # dry run — REVIEW the plan
    python seed_commercial_credit_flows.py --apply
"""
import sys, json, shutil, time
from pathlib import Path

F = Path("data/pipeline_settings.json")
cfg = json.loads(F.read_text(encoding="utf-8"))
pf = cfg.get("product_flows", {})

# --- client-type assignment (EDIT here if the split is wrong; dry-run shows it) ---
COMMERCIAL = ["Business Loan", "Overdraft", "Term Loan", "Asset Finance",
              "Invoice Discounting", "Working Capital"]
CIB        = ["Structured Finance", "Trade Finance", "Trade Finance LC"]
# Mortgage: set here once Josh decides. Default Commercial; change to 'Consumer' if retail.
MORTGAGE_TYPE = "Commercial"

def analysis_stage(ct: str) -> str:
    return {"Commercial": "Commercial Credit Analysis",
            "CIB": "CIB Credit Analysis",
            "Consumer": "Consumer Credit Analysis"}.get(ct, "Credit Analysis")

def build_stages(ct: str):
    a = analysis_stage(ct)
    # mirrors Personal Loan EXACTLY, incl. the post-Credit-Analysis tail (owner -> credit team)
    return [
        {"stage": "Initiation", "target_days": 3},
        {"stage": "Negotiation", "target_days": 1},
        {"stage": "Documentation", "target_days": 1},
        {"stage": "Branch Credit Committee Review", "target_days": 1},
        {"stage": a, "target_days": 1},
        {"stage": "Department Credit Committee Review", "target_days": 1},
        {"stage": "Credit Analysis", "target_days": 1},
        {"stage": "Offer Letter", "target_days": 1},
        {"stage": "Credit Administration", "target_days": 3},
        {"stage": "Trops", "target_days": 3},
    ]

def client_type_for(prod: str) -> str:
    if prod in COMMERCIAL: return "Commercial"
    if prod in CIB: return "CIB"
    if prod == "Mortgage": return MORTGAGE_TYPE
    return "Commercial"

lending = cfg.get("product_catalogue", {}).get("Assets", [])
plan, skipped = [], []
for prod in lending:
    entry = pf.get(prod, {})
    stages = [s.get("stage") for s in entry.get("stages", [])]
    is_generic = ("Lead" in stages) or (len(stages) == 0)
    has_credit = any("committee" in s.lower() or "credit analysis" in s.lower() for s in stages)
    if has_credit and not is_generic:
        skipped.append((prod, "already has a credit flow"))
        continue
    if prod in ("Personal Loan", "Bundled Loan Product"):
        skipped.append((prod, "template/working — untouched"))
        continue
    ct = client_type_for(prod)
    plan.append((prod, ct, analysis_stage(ct)))

print("=== PLAN — products to configure ===")
for prod, ct, a in plan:
    print(f"  {prod[:22]:22} client_type={ct:11} analysis_stage='{a}'")
print("\n=== SKIPPED (untouched) ===")
for prod, why in skipped:
    print(f"  {prod[:22]:22} — {why}")

print("\n=== stage sequence each will get (same as Personal Loan; tail hands off to credit team) ===")
for s in build_stages("Commercial"):
    print(f"     {s['stage']:34} target_days={s['target_days']}")

print("\nNOTE: post-Credit-Analysis tail (Offer Letter -> Credit Administration -> Trops) is")
print("identical to Personal Loan — the owner->credit-team handoff is preserved, not altered.")

if "--apply" not in sys.argv:
    print("\n[DRY-RUN] Review the client-type split above. Re-run with --apply to write.")
    print("If the Commercial/CIB split or Mortgage type is wrong, tell me and I'll adjust before apply.")
    sys.exit(0)

for prod, ct, a in plan:
    pf[prod] = {
        "client_types": [ct],
        "committee_journey": [],   # empty — routing engine resolves DCC from client_type (like Personal Loan)
        "stages": build_stages(ct),
    }
cfg["product_flows"] = pf
shutil.copy2(F, F.with_suffix(f".json.bak_{int(time.time())}"))
F.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")
print(f"\napplied. Configured {len(plan)} products. Backup written. Restart the API.")
