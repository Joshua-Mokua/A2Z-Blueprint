#!/usr/bin/env python3
"""A2Z MIS 360 — end-to-end smoke test.

Logs in as each persona and exercises Portfolio, Referrals, Daily Log, validation
scope, custodian access, and cross-persona isolation against a running API.

Run (with uvicorn up on :8502):
    python test_a2z_smoke.py
    python test_a2z_smoke.py --base http://localhost:8502
    python test_a2z_smoke.py --pass-frank EcoStaff0731 --pass-imm EcoStaff0716

Exit code 0 = all passed, 1 = one or more failures. Read-only (no writes).
"""
import argparse, json, sys
try:
    import requests
except ImportError:
    print("This test needs 'requests':  pip install requests --break-system-packages")
    sys.exit(2)

P = argparse.ArgumentParser()
P.add_argument("--base", default="http://localhost:8502")
P.add_argument("--pass-frank", default="EcoStaff0731")
P.add_argument("--pass-imm", default="EcoStaff0716")
P.add_argument("--custodian-user", default="")   # e.g. a CFO username, if you have one
P.add_argument("--custodian-pass", default="")
A = P.parse_args()
BASE = A.base.rstrip("/")

PASS = FAIL = 0
def ok(name, cond, detail=""):
    global PASS, FAIL
    if cond:
        PASS += 1; print(f"  [PASS] {name}")
    else:
        FAIL += 1; print(f"  [FAIL] {name}   {detail}")

def login(username, password):
    try:
        r = requests.post(f"{BASE}/api/auth/login", json={"username": username, "password": password}, timeout=15)
        if r.status_code != 200:
            return None, f"HTTP {r.status_code}: {r.text[:120]}"
        return r.json().get("access_token"), None
    except Exception as e:
        return None, str(e)

def get(token, path):
    try:
        r = requests.get(f"{BASE}{path}", headers={"Authorization": f"Bearer {token}"}, timeout=30)
        return r.status_code, (r.json() if r.headers.get("content-type","").startswith("application/json") else r.text)
    except Exception as e:
        return -1, str(e)

print(f"A2Z smoke test  →  {BASE}\n")

# ---------- 0. Health ----------
print("0. Health")
try:
    h = requests.get(f"{BASE}/api/health", timeout=10)
    ok("API health 200", h.status_code == 200, f"got {h.status_code}")
except Exception as e:
    ok("API health reachable", False, str(e)); print("\nAPI not reachable — is uvicorn running on :8502?"); sys.exit(1)

# ---------- 1. Logins ----------
print("\n1. Logins")
ftok, ferr = login("frank0731", A.pass_frank)
ok("Frank login", ftok is not None, ferr or "")
itok, ierr = login("immaculate0716", A.pass_imm)
ok("Immaculate login", itok is not None, ierr or "")
ctok = None
if A.custodian_user:
    ctok, cerr = login(A.custodian_user, A.custodian_pass)
    ok(f"Custodian login ({A.custodian_user})", ctok is not None, cerr or "")

if not ftok or not itok:
    print("\nCore logins failed — fix credentials (try --pass-frank / --pass-imm) and re-run.")
    print(f"\nSummary: {PASS} passed, {FAIL} failed."); sys.exit(1)

# ---------- 2. auth/me ----------
print("\n2. Identity")
sc, me = get(ftok, "/api/auth/me")
ok("Frank /auth/me 200", sc == 200, str(me)[:120])
ok("Frank username correct", isinstance(me, dict) and me.get("username") == "frank0731", str(me)[:120])

# ---------- 3. Portfolio (Frank, RM) ----------
print("\n3. Portfolio — Frank (RM)")
sc, pf = get(ftok, "/api/cbs/portfolio")
ok("Frank portfolio 200", sc == 200, str(pf)[:120])
fsum = (pf or {}).get("summary", {}) if isinstance(pf, dict) else {}
ok("Frank has accounts (>0)", fsum.get("accounts", 0) > 0, f"accounts={fsum.get('accounts')}")
ok("Frank is_manager == False", (pf or {}).get("is_manager") is False)
for k in ("deposits", "loans", "pipeline_value", "dormant_pct", "npl_accounts", "deposit_movement"):
    ok(f"summary has '{k}'", k in fsum)
ok("Frank YTD growth present (baseline populated)", fsum.get("deposit_movement") is not None,
   "deposit_movement is None — run populate_per_rm_baseline.py")
frank_accts = fsum.get("accounts", 0)
sample_cif = ((pf or {}).get("accounts") or [{}])[0].get("cif") if isinstance(pf, dict) else None

# ---------- 4. Customer 360 ----------
print("\n4. Customer 360")
if sample_cif:
    sc, cust = get(ftok, f"/api/cbs/customers/{sample_cif}")
    ok("Customer profile 200", sc == 200, str(cust)[:120])
    sc, accs = get(ftok, f"/api/cbs/customers/{sample_cif}/accounts")
    ok("Customer accounts 200", sc == 200, str(accs)[:120])
    ok("Customer has >=1 account", isinstance(accs, dict) and len(accs.get("accounts", [])) >= 1)
else:
    ok("Customer 360 (sample CIF found)", False, "no CIF in Frank's book")

# ---------- 5. Portfolio (Immaculate, consolidated) ----------
print("\n5. Portfolio — Immaculate (branch consolidated)")
sc, ipf = get(itok, "/api/cbs/portfolio")
ok("Immaculate portfolio 200", sc == 200, str(ipf)[:120])
isum = (ipf or {}).get("summary", {}) if isinstance(ipf, dict) else {}
ok("Immaculate is_manager == True", (ipf or {}).get("is_manager") is True)
ok("Immaculate view == consolidated", (ipf or {}).get("view") == "consolidated", f"view={(ipf or {}).get('view')}")
team = (ipf or {}).get("team", [])
ok("Immaculate team has >1 staff", len(team) > 1, f"team={len(team)}")
ok("Consolidated accounts > Frank's", isum.get("accounts", 0) > frank_accts, f"{isum.get('accounts')} vs {frank_accts}")
ok("Branch-unallocated card present", (ipf or {}).get("branch_unallocated") is not None,
   "branch_unallocated None — check branch-name→code match")
bu = (ipf or {}).get("branch_unallocated") or {}
ok("Branch-unallocated has accounts", bu.get("accounts", 0) > 0, f"unallocated={bu.get('accounts')}")

# ---------- 6. Portfolio staff selector (drill into Frank) ----------
print("\n6. Portfolio selector (Immaculate → Frank 300057)")
sc, drill = get(itok, "/api/cbs/portfolio?staff_code=300057")
ok("Selector drill 200", sc == 200, str(drill)[:120])
ok("Selector view == individual", (drill or {}).get("view") == "individual", f"view={(drill or {}).get('view')}")
ok("Drill accounts == Frank's book", (drill or {}).get("summary", {}).get("accounts") == frank_accts,
   f"{(drill or {}).get('summary', {}).get('accounts')} vs {frank_accts}")
ok("Drill hides branch-unallocated", (drill or {}).get("branch_unallocated") is None)

# ---------- 7. Referrals ----------
print("\n7. Referrals")
for path in ("/api/pipeline/referrals/incoming", "/api/pipeline/referrals/team"):
    sc, _ = get(ftok, path)
    ok(f"GET {path} 200 (Frank)", sc == 200, f"got {sc}")
# department analytics is EXEC-only (Chief/Director/MD) by design — both RM and BM denied
sc, _ = get(ftok, "/api/pipeline/referrals/analytics/by-department")
ok("by-department 403 for Frank (RM) — correct isolation", sc == 403, f"got {sc}")
sc, _ = get(itok, "/api/pipeline/referrals/analytics/by-department")
ok("by-department 403 for Immaculate (BM) — exec-only, correct", sc == 403, f"got {sc}")

# ---------- 8. Daily Log ----------
print("\n8. Daily Log")
for path in ("/api/branch-log/fields", "/api/branch-log/config",
             "/api/branch-log/ranking?days=30", "/api/branch-log/auto-activities"):
    sc, body = get(ftok, path)
    ok(f"GET {path} 200", sc == 200, f"got {sc}")
sc, fields = get(ftok, "/api/branch-log/fields")
ok("fields carry 'weight'", isinstance(fields, dict) and all("weight" in f for f in fields.get("fields", [])[:3]))

# ---------- 9. Validation scope (Immaculate = branch subtree) ----------
print("\n9. Validation scope")
sc, pend = get(itok, "/api/branch-log/pending")
ok("Immaculate /pending 200 (manager)", sc == 200, f"got {sc}")
sc, hist = get(itok, "/api/branch-log/history?days=30")
ok("Immaculate history 200 (subtree)", sc == 200, f"got {sc}")

# ---------- 10. Cross-persona isolation ----------
print("\n10. Isolation (Frank is NOT a manager)")
sc, fpend = get(ftok, "/api/branch-log/pending")
ok("Frank /pending forbidden (403)", sc == 403, f"got {sc} (non-managers shouldn't validate)")

# ---------- 11. Custodian (optional) ----------
if ctok:
    print("\n11. Custodian full-data view")
    sc, cpf = get(ctok, "/api/cbs/portfolio")
    ok("Custodian portfolio 200", sc == 200, f"got {sc}")
    csum = (cpf or {}).get("summary", {}) if isinstance(cpf, dict) else {}
    ok("Custodian sees a large book (> branch)", csum.get("accounts", 0) >= isum.get("accounts", 0),
       f"{csum.get('accounts')} vs branch {isum.get('accounts')}")
    sc, _ = get(ctok, "/api/pipeline/referrals/team")
    ok("Custodian referrals/team 200", sc == 200, f"got {sc}")
    sc, _ = get(ctok, "/api/pipeline/referrals/analytics/by-department")
    ok("Custodian by-department 200 (exec/chief role)", sc == 200, f"got {sc}")
else:
    print("\n11. Custodian full-data view — SKIPPED (pass --custodian-user/--custodian-pass to test)")

# ---------- Summary ----------
print("\n" + "=" * 48)
print(f"RESULT: {PASS} passed, {FAIL} failed.")
print("=" * 48)
sys.exit(0 if FAIL == 0 else 1)
