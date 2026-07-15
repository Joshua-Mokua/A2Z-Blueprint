#!/usr/bin/env python3
"""Re-tag the synthetic CBS onto the REAL staff register, by branch.

The synthetic CBS uses rm_codes 300001-300247; the register is now KE/CN-coded, so
every portfolio is empty until the accounts point at real people. This rewrites
cbs_data/accounts.csv and cbs_data/customers.csv so that, PER BRANCH:

  relationship_manager_code (= FLEXCUBE acc_ofcr)  -> a real KE manager in that branch
  introducer_code           (= FLEXCUBE INTRODUCER)-> a real KE/CN introducer, usually
                                                      the same branch, sometimes another
                                                      (a salesperson can introduce cross-
                                                      segment). Support roles included.

It ADDS the introducer_code column (populated now, surfaced in Portfolio later) so the
managed-vs-introduced split needs no second CBS rewrite.

Optionally down-samples to ~200,000 accounts (Ecobank's real scale) for a faster,
more realistic demo: --target 200000

Reads the register from data/staff_register.xlsx (the projection of PostgreSQL).
Dry-run by default; --apply writes (backing up the originals first).

    python retag_cbs.py                      # plan only
    python retag_cbs.py --target 200000      # plan, down-sampled
    python retag_cbs.py --target 200000 --apply
"""
import json, os, sys, shutil, random
from pathlib import Path
from datetime import datetime

CBS = Path("cbs_data")
ACCOUNTS = CBS / "accounts.csv"
CUSTOMERS = CBS / "customers.csv"
BRANCHES = CBS / "branches.json"
REGISTER = Path("data/staff_register.xlsx")
SEED = 42

# roles eligible to MANAGE an account (acc_ofcr) — customer-owning roles
MANAGER_ROLE_HINTS = (
    "relationship manager", "relationship officer", "branch manager",
    "premier", "sme", "corporate", "public sector", "employee schemes",
    "customer service manager", "head of direct",
)
# roles eligible to INTRODUCE (INTRODUCER) — sales + support + DSAs
INTRODUCER_ROLE_HINTS = MANAGER_ROLE_HINTS + (
    "direct sales agent", "branch dsa team lead", "bancassurance",
    "agency", "business development", "digital sales",
)

def _arg(flag, default=None, cast=str):
    if flag in sys.argv:
        i = sys.argv.index(flag)
        if i + 1 < len(sys.argv):
            return cast(sys.argv[i + 1])
    return default

def load_register():
    import pandas as pd
    df = pd.read_excel(REGISTER, dtype=str).fillna("")
    people = []
    for _, r in df.iterrows():
        code = str(r.get("Staff Code") or "").strip()
        if not code:
            continue
        people.append({"code": code, "role": str(r.get("Role") or ""),
                       "branch": str(r.get("Branch") or "").strip(),
                       "name": str(r.get("Staff Name") or "")})
    return people

def branch_code_to_name():
    """branches.json -> {branch_code: branch_name}. Handles list or dict shapes."""
    raw = json.loads(BRANCHES.read_text(encoding="utf-8"))
    out = {}
    if isinstance(raw, dict):
        # could be {name: code} or {code: {...}} — normalise
        for k, v in raw.items():
            if isinstance(v, str):
                out[str(v)] = str(k)                 # {name: code}
            elif isinstance(v, dict):
                out[str(k)] = str(v.get("name") or v.get("branch_name") or k)
    elif isinstance(raw, list):
        for b in raw:
            c = str(b.get("branch_code") or b.get("code") or "")
            n = str(b.get("branch_name") or b.get("name") or "")
            if c:
                out[c] = n
    return out

def main():
    apply = "--apply" in sys.argv
    target = _arg("--target", None, int)
    random.seed(SEED)
    for p in (ACCOUNTS, CUSTOMERS, BRANCHES, REGISTER):
        if not p.exists():
            print(f"MISSING {p}"); sys.exit(1)
    import pandas as pd
    _pd = pd

    people = load_register()
    b2n = branch_code_to_name()
    n2b = {v: k for k, v in b2n.items()}
    print(f"register: {len(people)} staff | branches.json: {len(b2n)} codes")

    # Pools keyed by the register BRANCH NAME directly (the CBS branches.json is
    # fictional and shares no names with the real 16, so any name->code lookup via it
    # returns nothing — that was the earlier bug where only Head Office got a pool).
    mgr_pool, intro_pool = {}, {}
    for p in people:
        b = p["branch"]
        if not b or b == "Head Office":
            continue
        rl = p["role"].lower()
        if any(h in rl for h in MANAGER_ROLE_HINTS):
            mgr_pool.setdefault(b, []).append(p["code"])
        if any(h in rl for h in INTRODUCER_ROLE_HINTS):
            intro_pool.setdefault(b, []).append(p["code"])
    # a branch with sales staff but no "manager"-hinted role still needs a manager:
    # fall back to anyone customer-facing in that branch, else the branch's introducers
    for b, ip in intro_pool.items():
        if b not in mgr_pool and ip:
            mgr_pool[b] = list(ip)
    # bank-wide introducer fallback (head-office sales, cross-segment)
    intro_any = [p["code"] for p in people
                 if any(h in p["role"].lower() for h in INTRODUCER_ROLE_HINTS)]
    mgr_any = [p["code"] for p in people
               if any(h in p["role"].lower() for h in MANAGER_ROLE_HINTS)]

    # The synthetic CBS was generated on a FICTIONAL branch network (Bungoma, Diani,
    # Wajir...) that does not match Ecobank's real 16. So we do NOT try to join on the
    # CBS branch — we re-stamp each account onto a REAL register branch (weighted by how
    # many staff each branch has, so busy branches get more accounts) and assign the
    # manager + introducer from THAT branch. Branch, manager and introducer stay coherent.
    real_branches = [b for b in mgr_pool if mgr_pool[b]]     # register branch names w/ a manager
    if not real_branches:
        print("ABORT: no register branch has a manager-eligible staffer."); sys.exit(1)
    # weight = number of managers in the branch (proxy for branch size)
    weights = [len(mgr_pool[b]) for b in real_branches]
    print(f"real branches with a manager pool: {len(real_branches)}")
    for b, w in sorted(zip(real_branches, weights), key=lambda x: -x[1]):
        print(f"   {b:18} managers={w:2}  introducers={len(intro_pool.get(b, []))}")

    # map real branch NAME -> a CBS branch_code to stamp (reuse the CBS codes so the
    # rest of the app, which keys on branch_code, keeps working). Build name->code here.
    real_code = {}
    for i, b in enumerate(real_branches, 1):
        real_code[b] = f"ECO{i:03d}"       # synthetic-but-stable code per real branch

    print(f"\nloading {ACCOUNTS} ...")
    acc = pd.read_csv(ACCOUNTS, dtype=str, low_memory=False).fillna("")
    print(f"  {len(acc):,} accounts, columns: {len(acc.columns)}")
    if target and target < len(acc):
        acc = acc.sample(n=target, random_state=SEED).reset_index(drop=True)
        print(f"  down-sampled to {len(acc):,}")

    CROSS = 0.40
    n = len(acc)
    # assign each account a real branch by weighted choice, then mgr + introducer from it
    chosen_branch = random.choices(real_branches, weights=weights, k=n)
    br_name, br_code, rm_new, intro_new = [], [], [], []
    for b in chosen_branch:
        mp = mgr_pool[b]; ip = intro_pool.get(b) or mp
        m = random.choice(mp)
        if random.random() < CROSS and len(ip) > 1:
            i = random.choice([x for x in ip if x != m] or ip)
        else:
            i = m
        br_name.append(b); br_code.append(real_code[b])
        rm_new.append(m); intro_new.append(i)
    acc["branch_name"] = br_name
    acc["branch_code"] = br_code
    acc["relationship_manager_code"] = rm_new
    acc["introducer_code"] = intro_new
    miss_branch = 0

    # ---- REALISM PASS: vary the book so the demo tells a story, not a flat sheet ----
    # Each manager gets a random "profile" that skews their accounts:
    #   * npl_tier      -> some RMs run clean books, a few carry problem loans
    #   * dormancy_tier -> pockets of dormant accounts, not uniform
    #   * concentration -> a handful of accounts per branch hold outsized balances
    if "--vary" in sys.argv or "--apply" in sys.argv:
        import numpy as _np
        _np.random.seed(SEED)
        mgrs = list(dict.fromkeys(rm_new))
        # profile per manager
        npl_tier = {m: _np.random.choice(["clean", "clean", "clean", "watch", "stress"])
                    for m in mgrs}
        dorm_tier = {m: _np.random.choice(["low", "low", "mid", "high"]) for m in mgrs}
        DORM_RATE = {"low": 0.05, "mid": 0.18, "high": 0.35}
        NPL_RATE  = {"clean": 0.01, "watch": 0.06, "stress": 0.18}

        rng = _np.random.random(len(acc))
        rmcol = acc["relationship_manager_code"].values
        # dormancy
        if "dormancy_status" in acc.columns:
            dorm = []
            for i, m in enumerate(rmcol):
                dorm.append("Dormant" if rng[i] < DORM_RATE[dorm_tier.get(m, "low")] else "Active")
            acc["dormancy_status"] = dorm
        # NPL only on accounts that actually carry a loan
        if "npl_status" in acc.columns and "loan_outstanding" in acc.columns:
            lo = _pd.to_numeric(acc["loan_outstanding"], errors="coerce").fillna(0).values
            rng2 = _np.random.random(len(acc))
            npl = []
            npl_days = []
            for i, m in enumerate(rmcol):
                if lo[i] > 0 and rng2[i] < NPL_RATE[npl_tier.get(m, "clean")]:
                    npl.append("NPL"); npl_days.append(int(_np.random.choice([95, 120, 180, 365])))
                else:
                    npl.append("Performing"); npl_days.append(0)
            acc["npl_status"] = npl
            if "npl_days" in acc.columns:
                acc["npl_days"] = npl_days
        # concentration: top ~1% of accounts per branch get a balance uplift
        if "current_balance" in acc.columns:
            bal = _pd.to_numeric(acc["current_balance"], errors="coerce").fillna(0).values.astype(float)
            whales = _np.random.random(len(acc)) < 0.01
            bal[whales] = bal[whales] * _np.random.uniform(8, 25, size=whales.sum())
            acc["current_balance"] = _np.round(bal, 2)
            if "available_balance" in acc.columns:
                acc["available_balance"] = _np.round(bal * 0.95, 2)
        print("  realism pass: varied dormancy / NPL / concentration by RM profile")
        # quick spread report
        if "npl_status" in acc.columns:
            n_npl = int((acc["npl_status"] == "NPL").sum())
            n_dorm = int((acc["dormancy_status"] == "Dormant").sum()) if "dormancy_status" in acc.columns else 0
            print(f"     NPL accounts: {n_npl:,} ({n_npl/len(acc)*100:.1f}%) | dormant: {n_dorm:,} ({n_dorm/len(acc)*100:.1f}%)")

    # report
    import collections
    mc = collections.Counter(rm_new)
    print(f"\nassigned {len(acc):,} accounts")
    print(f"  distinct managers    : {len(mc)}")
    print(f"  distinct introducers : {len(set(intro_new))}")
    print(f"  same person mgr+intro: {sum(1 for a,b in zip(rm_new,intro_new) if a==b)/len(acc)*100:.0f}%")
    print(f"  accounts whose branch had no manager pool (used bank-wide): {miss_branch:,}")
    print("  top 5 books:")
    for code, n in mc.most_common(5):
        nm = next((p["name"] for p in people if p["code"] == code), "?")
        print(f"     {code:8} {nm[:26]:26} {n:,} accounts")

    if not apply:
        print("\n[DRY-RUN] nothing written. Re-run with --apply.")
        return

    ts = datetime.now().strftime("%Y%m%d-%H%M%S")
    shutil.copyfile(ACCOUNTS, str(ACCOUNTS) + f".pre_retag_{ts}")
    acc.to_csv(ACCOUNTS, index=False)
    print(f"\nwrote {ACCOUNTS} ({len(acc):,} rows) [backup .pre_retag_{ts}]")

    # Rewrite branches.json so its branch_name/branch_code match the real 16 the
    # accounts now carry — otherwise branch_code_for_name (which matches on
    # branch_name) can't resolve them, and consolidated/branch-unallocated views break.
    reg_region = {}
    for p in people:
        pass
    import pandas as _pd
    _regdf = _pd.read_excel(REGISTER, dtype=str).fillna("")
    name_region = {}
    for _, rr in _regdf.iterrows():
        bn = str(rr.get("Branch") or "").strip()
        rg = str(rr.get("Region") or "").strip()
        if bn and bn not in name_region:
            name_region[bn] = rg
    new_branches = [{"branch_code": "BRN001", "branch_name": "Head Office",
                     "region": "Nairobi", "branch_type": "HO", "tier": 1}]
    for b in real_branches:
        new_branches.append({"branch_code": real_code[b], "branch_name": b,
                             "region": name_region.get(b, ""), "branch_type": "Branch", "tier": 2})
    shutil.copyfile(BRANCHES, str(BRANCHES) + f".pre_retag_{ts}")
    BRANCHES.write_text(json.dumps(new_branches, indent=2), encoding="utf-8")
    print(f"wrote {BRANCHES} ({len(new_branches)} real branches)")

    # customers: re-point relationship_manager_code the same way, by branch
    cust = pd.read_csv(CUSTOMERS, dtype=str, low_memory=False).fillna("")
    if "relationship_manager_code" in cust.columns:
        cb = random.choices(real_branches, weights=weights, k=len(cust))
        cust["relationship_manager_code"] = [random.choice(mgr_pool[b]) for b in cb]
        if "branch_name" in cust.columns:
            cust["branch_name"] = cb
        if "branch_code" in cust.columns:
            cust["branch_code"] = [real_code[b] for b in cb]
        shutil.copyfile(CUSTOMERS, str(CUSTOMERS) + f".pre_retag_{ts}")
        cust.to_csv(CUSTOMERS, index=False)
        print(f"wrote {CUSTOMERS} ({len(cust):,} rows)")
    print("\nRestart uvicorn (:8502) to reload CBS. Portfolio should populate.")

if __name__ == "__main__":
    main()
