#!/usr/bin/env python3
"""Populate per_rm in cbs_baseline_2025_Dec_31.json — each RM's deposits/loans/
accounts — so Portfolio's YTD deposit-growth lights up (it reads per_rm[code].deposits).

Modes:
  (default)          snapshot CURRENT per-RM deposits as the baseline. Real, honest;
                     growth reads ~0 now and moves as the book changes going forward.
  --factor 0.12      backdate the baseline to current/(1+0.12) so the current book
                     shows ~+12% growth — illustrative for a demo/pitch.

Backs up the baseline (.pre_perrm_*). Dry-run unless --apply. Run from repo root."""
import json, os, sys
from datetime import datetime

LOAN_WORDS = ("loan", "facility", "lpo", "mortgage", "advance", "overdraft")

def find(*cands):
    for c in cands:
        if os.path.exists(c):
            return c
    return None

def main():
    import pandas as pd
    acc = find("cbs_data/accounts.csv", "data/cbs_data/accounts.csv", "a2z/cbs_data/accounts.csv")
    base = find("data/cbs_baseline_2025_Dec_31.json", "a2z/data/cbs_baseline_2025_Dec_31.json")
    if not acc or not base:
        print("accounts.csv or baseline json not found"); sys.exit(1)
    factor = 0.0
    if "--factor" in sys.argv:
        try: factor = float(sys.argv[sys.argv.index("--factor") + 1])
        except Exception: factor = 0.0

    print(f"reading {acc} ...")
    df = pd.read_csv(acc, usecols=["relationship_manager_code", "account_type_name", "current_balance"],
                     dtype={"relationship_manager_code": str, "account_type_name": str})
    df["rm"] = df["relationship_manager_code"].astype(str).str.strip()
    df["bal"] = pd.to_numeric(df["current_balance"], errors="coerce").fillna(0.0)
    tl = df["account_type_name"].astype(str).str.lower()
    df["is_loan"] = tl.str.contains("|".join(LOAN_WORDS), regex=True, na=False)
    df = df[df["rm"] != ""]

    dep = df[~df["is_loan"]].groupby("rm")["bal"].sum()
    loan = df[df["is_loan"]].groupby("rm")["bal"].sum()
    cnt = df.groupby("rm").size()

    per_rm = {}
    for rm in cnt.index:
        d = float(dep.get(rm, 0.0)); l = float(loan.get(rm, 0.0))
        if factor:
            d = d / (1.0 + factor); l = l / (1.0 + factor)
        per_rm[rm] = {"deposits": round(d, 2), "loans": round(l, 2), "accounts": int(cnt[rm])}

    print(f"computed per_rm for {len(per_rm)} RM code(s). factor={factor}")
    sample = list(per_rm.items())[:3]
    for rm, v in sample:
        print(f"  {rm}: deposits={v['deposits']:,.0f}  loans={v['loans']:,.0f}  accounts={v['accounts']}")

    if "--apply" not in sys.argv:
        print("\n[DRY-RUN] add --apply to write per_rm into the baseline"
              + ("  (tip: --factor 0.12 to show ~12% growth for the demo)" if not factor else ""))
        return

    import shutil
    shutil.copyfile(base, base + f".pre_perrm_{datetime.now():%Y%m%d-%H%M%S}")
    bl = json.load(open(base, encoding="utf-8"))
    bl["per_rm"] = per_rm
    bl["per_rm_generated_at"] = datetime.now().isoformat()
    bl["per_rm_factor"] = factor
    json.dump(bl, open(base, "w", encoding="utf-8"), ensure_ascii=False, indent=2)
    print(f"\nwrote per_rm ({len(per_rm)} RMs) into {base}. Restart uvicorn — Portfolio YTD growth now lights up.")

if __name__ == "__main__":
    main()
