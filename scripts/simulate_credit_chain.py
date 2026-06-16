"""A2Z MIS 360 — end-to-end credit-chain simulation & stress harness.

Drives the LIVE API the way the React app does: real JWT logins, real deals,
real state transitions. Zero external dependencies (stdlib urllib + json), so it
runs in the project venv untouched.

Run the API first (python -m utils.api), then:

  python scripts\\simulate_credit_chain.py                 # happy path + guards + scope
  python scripts\\simulate_credit_chain.py --volume 120    # + stress: 120 deals, timed
  python scripts\\simulate_credit_chain.py --base http://localhost:8502

Personas (override at the top of this file if your test logins differ):
  OWNER   — deal owner / RM            (creates, submits, signs offer)
  MANAGER — owner's line manager       (assigns, decides, validates, resolves)
  ADMIN   — broad rights              (used where role separation isn't the focus)

Exit code 0 if every assertion passed, 1 otherwise — so CI/pre-client gates can
consume it.
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

# ── Personas (edit to match your seeded test logins) ────────────────────
PERSONAS = {
    "OWNER":   {"username": "frank0731",     "password": "EcoStaff0731"},
    "MANAGER": {"username": "immaculate0716", "password": "EcoStaff0716"},
    "ADMIN":   {"username": "william001",      "password": "EcoStaff0001"},
}

# Committee charter members from the default config (scripts/add_committee_config.py)
COMMITTEE_MEMBERS = ["m1", "m2", "m3", "m4", "m5"]

RESULTS: list[dict] = []


def _req(base, method, path, token=None, body=None, timeout=30):
    url = base.rstrip("/") + path
    data = json.dumps(body).encode() if body is not None else None
    req = urllib.request.Request(url, data=data, method=method)
    req.add_header("Content-Type", "application/json")
    if token:
        req.add_header("Authorization", f"Bearer {token}")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            raw = r.read().decode()
            return r.status, (json.loads(raw) if raw else {})
    except urllib.error.HTTPError as e:
        raw = e.read().decode()
        try:
            payload = json.loads(raw)
        except Exception:
            payload = {"detail": raw[:300]}
        return e.code, payload
    except Exception as e:  # connection refused etc.
        return 0, {"detail": f"{type(e).__name__}: {e}"}


_TOKEN_CACHE: dict = {}

def login(base, persona_key):
    # Cache tokens per persona so we hit /login once each — avoids the
    # per-IP login rate limit (10/min) during a full run.
    if persona_key in _TOKEN_CACHE:
        return _TOKEN_CACHE[persona_key]
    p = PERSONAS[persona_key]
    st, body = _req(base, "POST", "/api/auth/login", body=p)
    if st == 429:  # rate-limited — wait out the window once, then retry
        print(f"  [rate-limited on {persona_key} login — waiting 61s]")
        time.sleep(61)
        st, body = _req(base, "POST", "/api/auth/login", body=p)
    tok = body.get("access_token") or body.get("token")
    if st == 200 and tok:
        _TOKEN_CACHE[persona_key] = tok
    if st != 200 or not tok:
        print(f"  [LOGIN FAIL] {persona_key} ({p['username']}) -> {st} {body.get('detail','')}")
        return None
    return tok


def step(name, expect, actual_status, payload=None, note=""):
    ok = (actual_status == expect) if isinstance(expect, int) else (actual_status in expect)
    RESULTS.append({"step": name, "expect": expect, "got": actual_status, "ok": ok, "note": note})
    flag = "PASS" if ok else "FAIL"
    extra = f" :: {note}" if note else ""
    detail = ""
    if not ok and isinstance(payload, dict):
        detail = f"  <- {str(payload.get('detail', payload))[:160]}"
    print(f"  [{flag}] {name}  (expect {expect}, got {actual_status}){extra}{detail}")
    return ok


# ── Happy path: full chain end to end ───────────────────────────────────

def happy_path(base, committee=False):
    print(f"\n=== HAPPY PATH ({'committee' if committee else 'authority'} route) ===")
    admin = login(base, "ADMIN")
    owner = login(base, "OWNER") or admin
    manager = login(base, "MANAGER") or admin
    if not admin:
        step("admin login", 200, 0, note="cannot proceed without admin")
        return

    # 1. Create a deal (owner). Asset product so it has the Credit Assessment gate.
    deal_body = {
        "client_name": f"SIM Acme Ltd {datetime.now():%H%M%S}",
        "client_type": "Business",
        "product_type": "Term Loan",
        "deal_value": 150000000 if committee else 5000000,
        "stage": "Lead",
        "segment": "SME",
        "sector": "Manufacturing",
    }
    st, body = _req(base, "POST", "/api/pipeline/deals", owner, deal_body)
    step("pipeline: create deal", (200, 201), st, body)
    deal_id = body.get("id") or body.get("deal", {}).get("id")
    if not deal_id:
        step("deal id returned", True, False, body, "no id -> aborting chain")
        return
    print(f"      deal_id = {deal_id}")

    # 1b. (P4-1b) FX stamping — the created deal should carry currency_book.
    # KES deal -> LCY, fx_rate 1.0. Non-fatal: just a green check.
    _book = body.get("currency_book") or body.get("deal", {}).get("currency_book")
    step("pipeline: deal carries currency_book (FX stamp)", True,
         _book in ("LCY", "FCY"), {"currency_book": _book})

    # 2. Advance to Credit Assessment.
    for tgt in ["Contacted", "Qualified", "Application", "Credit Assessment"]:
        st, body = _req(base, "POST", f"/api/pipeline/deals/{deal_id}/advance",
                        owner, {"target_stage": tgt})
        step(f"pipeline: advance -> {tgt}", (200, 201), st, body)

    # 3. Submit with MISSING docs -> must be blocked (guard).
    st, body = _req(base, "POST", f"/api/pipeline/deals/{deal_id}/submit-to-credit",
                    owner, {"documents_provided": []})
    step("GUARD: submit with missing docs blocked", 400, st, body)

    # 4. Read the checklist, then submit with all docs -> deal auto-advances.
    st, chk = _req(base, "GET", f"/api/pipeline/deals/{deal_id}/credit-checklist", owner)
    required = chk.get("required", []) if isinstance(chk, dict) else []
    st, body = _req(base, "POST", f"/api/pipeline/deals/{deal_id}/submit-to-credit",
                    owner, {"documents_provided": required})
    step("pipeline: submit-to-credit (docs complete)", (200, 201), st, body,
         note=f"deal stage now: {body.get('stage')}")
    app_id = body.get("application_id")
    if not app_id:
        step("LMS app created on submit", True, False, body, "no application_id -> aborting")
        return
    print(f"      application_id = {app_id}")

    # 5. LMS: assign analyst (manager).
    st, body = _req(base, "POST", f"/api/lms/applications/{app_id}/assign",
                    manager, {"analyst_code": PERSONAS['MANAGER']['username'],
                              "analyst_name": "Sim Analyst"})
    step("lms: assign analyst", (200, 201), st, body)

    if committee:
        # 6c. Refer -> vote (quorum incl m2=CRO) -> resolve.
        st, body = _req(base, "POST", f"/api/lms/applications/{app_id}/committee/refer", manager)
        step("lms: refer to committee", (200, 201), st, body)
        for m, v in [("m1", "YES"), ("m2", "YES"), ("m3", "YES"), ("m4", "NO")]:
            st, body = _req(base, "POST", f"/api/lms/applications/{app_id}/committee/vote",
                            manager, {"member_id": m, "vote": v})
            step(f"lms: committee vote {m}={v}", (200, 201), st, body)
        st, body = _req(base, "POST", f"/api/lms/applications/{app_id}/committee/resolve",
                        manager, {})
        step("lms: committee resolve", (200, 201), st, body,
             note=f"status: {body.get('status')}")
    else:
        # 6a. Direct decision: approve.
        st, body = _req(base, "POST", f"/api/lms/applications/{app_id}/decision",
                        manager, {"verdict": "approved", "authority": "Branch Credit Manager",
                                  "reason": "Sim approval"})
        step("lms: decision approved", (200, 201), st, body, note=f"status: {body.get('status')}")

    # 7. Offer loop: sign (owner) -> validate (manager) -> confirm (manager).
    st, body = _req(base, "POST", f"/api/lms/applications/{app_id}/sign-offer",
                    owner, {"attachment_filename": "signed_offer_sim.pdf"})
    step("lms: sign offer", (200, 201, 400), st, body, note=f"status: {body.get('status')}")
    st, body = _req(base, "POST", f"/api/lms/applications/{app_id}/validate-offer",
                    manager, {"approve": True})
    step("lms: validate offer", (200, 201, 400), st, body, note=f"status: {body.get('status')}")
    st, body = _req(base, "POST", f"/api/lms/applications/{app_id}/confirm-to-credit-admin",
                    manager, {})
    step("lms: confirm to credit admin", (200, 201, 400), st, body,
         note=f"status: {body.get('status')}")

    # 8. Credit Admin: find the case for this app.
    st, cases = _req(base, "GET", "/api/credit-admin/cases", admin)
    case_id = None
    for c in (cases.get("cases", []) if isinstance(cases, dict) else []):
        if c.get("application_id") == app_id:
            case_id = c.get("id")
            break
    step("credit-admin: case auto-created for app", True, bool(case_id),
         note=f"case_id={case_id}" if case_id else "no case found for app")
    if not case_id:
        return

    # 8b. (P4-2) Classify the facility as secured/debenture — proves the
    # classification endpoint end-to-end. Non-blocking (gate is P4-6).
    st, body = _req(base, "POST", f"/api/credit-admin/cases/{case_id}/classify-facility",
                    admin, {"facility_security_type": "secured", "security_subtype": "debenture"})
    step("credit-admin: classify facility (secured/debenture)", (200, 201), st, body)

    # 8c. (P4-3) Link collateral and confirm coverage + classification compute.
    st, body = _req(base, "POST", f"/api/credit-admin/cases/{case_id}/collateral/link",
                    admin, {"collateral_id": "SIMCOL1", "collateral_type": "Debenture",
                            "forced_sale_value": 999_000_000_000, "currency": "KES"})
    _case = body.get("case", {}) if isinstance(body, dict) else {}
    step("credit-admin: link collateral -> coverage computed", (200, 201), st, body)
    step("credit-admin: security_classification set", True,
         _case.get("security_classification") in
         ("unsecured", "partially_secured", "fully_secured", "over_secured"),
         {"classification": _case.get("security_classification"),
          "coverage": _case.get("coverage_ratio")})

    # 8d. (P4-4) Legal review: assign -> clear.
    st, body = _req(base, "POST", f"/api/credit-admin/cases/{case_id}/legal/assign",
                    admin, {"officer_code": "LO001", "officer_name": "SIM Legal Officer"})
    step("credit-admin: legal assign", (200, 201), st, body)
    st, body = _req(base, "POST", f"/api/credit-admin/cases/{case_id}/legal/outcome",
                    admin, {"outcome": "approved", "note": "sim clearance"})
    _lr = (body.get("case", {}) if isinstance(body, dict) else {}).get("legal_review", {})
    step("credit-admin: legal cleared", True, _lr.get("outcome") == "approved",
         {"legal_status": _lr.get("status"), "outcome": _lr.get("outcome")})

    # 9. GUARD: disburse before authorize -> blocked.
    st, body = _req(base, "POST", f"/api/credit-admin/cases/{case_id}/disburse",
                    admin, {"authority": "CA Manager"})
    step("GUARD: disburse before authorize blocked", (400, 403), st, body)

    # 10. Fulfill conditions, then two-layer authorize, then disburse.
    st, detail = _req(base, "GET", f"/api/credit-admin/cases/{case_id}", admin)
    conds = (detail.get("case", {}) or {}).get("conditions", []) if isinstance(detail, dict) else []
    for c in conds:
        ctype = c.get("type")
        if ctype and not c.get("fulfilled"):
            st, body = _req(base, "POST", f"/api/credit-admin/cases/{case_id}/conditions/fulfill",
                            admin, {"condition_type": ctype, "officer_name": "Sim Officer"})
            step(f"credit-admin: fulfill '{ctype}'", (200, 201), st, body)
    st, body = _req(base, "POST", f"/api/credit-admin/cases/{case_id}/request-authorization",
                    admin, {"note": "Sim layer-1"})
    step("credit-admin: request authorization (L1)", (200, 201, 400), st, body)
    st, body = _req(base, "POST", f"/api/credit-admin/cases/{case_id}/authorize",
                    admin, {"note": "Sim layer-2"})
    step("credit-admin: authorize (L2)", (200, 201, 400), st, body)
    st, body = _req(base, "POST", f"/api/credit-admin/cases/{case_id}/disburse",
                    admin, {"authority": "CA Manager", "comments": "Sim disburse"})
    step("credit-admin: disburse", (200, 201), st, body, note=f"status: {body.get('status')}")


# ── Scope guard: out-of-scope access blocked ────────────────────────────

def scope_guard(base):
    print("\n=== SCOPE GUARD ===")
    admin = login(base, "ADMIN")
    owner = login(base, "OWNER")
    if not (admin and owner):
        step("scope logins", True, False, note="need admin+owner")
        return
    # Owner should not see the full application list at manager scope, and a
    # random foreign deal id should 403/404 rather than leak.
    st, body = _req(base, "GET", "/api/pipeline/deals/D000000-not-yours", owner)
    step("GUARD: foreign deal id not leaked", (403, 404), st, body)


# ── MD dashboard sanity: assured split present ──────────────────────────

def dashboard_check(base):
    print("\n=== MD DASHBOARD (assured split) ===")
    admin = login(base, "ADMIN")
    if not admin:
        return
    st, body = _req(base, "GET", "/api/dashboard/md", admin)
    step("dashboard: md reachable", 200, st, body)
    pipe = body.get("pipeline", {}) if isinstance(body, dict) else {}
    step("dashboard: exposes validated_value (assured)", True, "validated_value" in pipe,
         note=f"validated={pipe.get('validated_value')}, sum={pipe.get('pipeline_value')}")


# ── Stress / volume ─────────────────────────────────────────────────────

def stress(base, n):
    print(f"\n=== STRESS: create {n} deals across products/branches ===")
    owner = login(base, "OWNER")
    if not owner:
        step("stress login", True, False)
        return
    products = ["Personal Loan", "Asset Finance", "Mortgage", "Working Capital",
                "Overdraft", "Trade Finance", "Term Loan", "Revolving Credit",
                "Seasonal Production Loan", "Equipment Finance"]
    t0 = time.time()
    ok = 0
    lat = []
    for i in range(n):
        s = time.time()
        st, body = _req(base, "POST", "/api/pipeline/deals", owner, {
            "client_name": f"SIM Bulk {i}",
            "client_type": "Business" if i % 2 else "Individual",
            "product_type": products[i % len(products)],
            "deal_value": 1_000_000 + (i * 250_000),
            "stage": "Lead",
        })
        lat.append((time.time() - s) * 1000)
        if st in (200, 201):
            ok += 1
    dt = time.time() - t0
    lat.sort()
    p50 = lat[len(lat) // 2] if lat else 0
    p95 = lat[int(len(lat) * 0.95)] if lat else 0
    step(f"stress: {ok}/{n} deals created", True, ok == n,
         note=f"{dt:.1f}s total, {ok/dt:.1f} deals/s, p50={p50:.0f}ms p95={p95:.0f}ms")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8502")
    ap.add_argument("--volume", type=int, default=0)
    ap.add_argument("--skip-committee", action="store_true")
    args = ap.parse_args()

    print(f"A2Z credit-chain simulation @ {args.base}  ({datetime.now():%Y-%m-%d %H:%M:%S})")
    # Reachability
    st, _ = _req(args.base, "GET", "/api/health")
    if st == 0:
        print("  API not reachable — start it with `python -m utils.api` first.")
        sys.exit(2)

    happy_path(args.base, committee=False)
    if not args.skip_committee:
        happy_path(args.base, committee=True)
    scope_guard(args.base)
    dashboard_check(args.base)
    if args.volume:
        stress(args.base, args.volume)

    # Summary
    total = len(RESULTS)
    passed = sum(1 for r in RESULTS if r["ok"])
    print("\n" + "=" * 60)
    print(f"SUMMARY: {passed}/{total} checks passed")
    fails = [r for r in RESULTS if not r["ok"]]
    if fails:
        print("FAILURES:")
        for r in fails:
            print(f"  - {r['step']} (expected {r['expect']}, got {r['got']})")
    print("=" * 60)
    sys.exit(0 if passed == total else 1)


if __name__ == "__main__":
    main()
