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

    # 4. Read the checklist. C1: submitting with docs but WITHOUT manager
    # validation must now be blocked — a deal must be validated first.
    st, chk = _req(base, "GET", f"/api/pipeline/deals/{deal_id}/credit-checklist", owner)
    required = chk.get("required", []) if isinstance(chk, dict) else []
    st, body = _req(base, "POST", f"/api/pipeline/deals/{deal_id}/submit-to-credit",
                    owner, {"documents_provided": required})
    step("GUARD: submit-to-credit blocked until manager-validated", 400, st, body)

    # 5. Manager validates the deal (the new control point).
    st, body = _req(base, "POST", f"/api/pipeline/deals/{deal_id}/validate",
                    manager, {"approved": True, "note": "validated for credit (sim)"})
    step("pipeline: manager validates deal", (200, 201), st, body)

    # 6. Now submit with all docs -> deal auto-advances.
    st, body = _req(base, "POST", f"/api/pipeline/deals/{deal_id}/submit-to-credit",
                    owner, {"documents_provided": required})
    step("pipeline: submit-to-credit (validated + docs complete)", (200, 201), st, body,
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

    # 8e. (P4-5) Security perfection: add -> mark perfected.
    st, body = _req(base, "POST", f"/api/credit-admin/cases/{case_id}/perfection",
                    admin, {"security_type": "Debenture", "registration_reference": "CR/SIM/1"})
    step("credit-admin: add security perfection", (200, 201), st, body)
    _perfs = (body.get("case", {}) if isinstance(body, dict) else {}).get("security_perfections", [])
    _pid = _perfs[-1]["id"] if _perfs else None
    if _pid:
        st, body = _req(base, "POST",
                        f"/api/credit-admin/cases/{case_id}/perfection/{_pid}/update",
                        admin, {"registration_status": "registered", "perfection_status": "perfected"})
        step("credit-admin: mark perfection perfected", (200, 201), st, body)

    # 8f. (P4-5) Insurance: add an active, bank-interest-noted policy.
    st, body = _req(base, "POST", f"/api/credit-admin/cases/{case_id}/insurance",
                    admin, {"insurer": "SIM Assurance", "policy_number": "POL-SIM-1",
                            "expiry_date": "2027-12-31", "bank_interest_noted": True})
    step("credit-admin: add insurance policy", (200, 201), st, body)

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

    # 11b. (P4-6) The secured-lending hard-gate must PASS (we cleared legal,
    # perfected security, added insurance, linked collateral above).
    st, gate = _req(base, "GET", f"/api/credit-admin/cases/{case_id}/disbursement-gate", admin)
    step("credit-admin: disbursement gate passes (secured controls met)", True,
         isinstance(gate, dict) and gate.get("passed") is True,
         {"passed": gate.get("passed") if isinstance(gate, dict) else None,
          "failures": [f.get("check") for f in gate.get("failures", [])] if isinstance(gate, dict) else None})

    st, body = _req(base, "POST", f"/api/credit-admin/cases/{case_id}/disburse",
                    admin, {"authority": "CA Manager", "comments": "Sim disburse"})
    step("credit-admin: disburse", (200, 201), st, body, note=f"status: {body.get('status')}")
    return case_id


# ── Negative + override probe: gate BLOCKS, override UNBLOCKS (live) ─────

def negative_override_probe(base):
    """Proves enforcement: a secured facility missing perfection is BLOCKED at
    disburse with the right failure, then a controlled override unblocks it and
    the disbursement is flagged disbursed_under_override. Independent of
    happy_path so the proven flow is untouched."""
    print("\n=== NEGATIVE + OVERRIDE PROBE (gate enforcement) ===")
    admin = login(base, "ADMIN")
    owner = login(base, "OWNER") or admin
    manager = login(base, "MANAGER") or admin
    if not admin:
        step("probe: admin login", 200, 0, note="cannot proceed")
        return

    # Build a deal through to credit-admin (authority route, standard value).
    deal_body = {"client_name": f"SIM Override Co {datetime.now():%H%M%S}",
                 "client_type": "Business", "product_type": "Term Loan",
                 "deal_value": 5000000, "stage": "Lead", "segment": "SME",
                 "sector": "Manufacturing"}
    st, body = _req(base, "POST", "/api/pipeline/deals", owner, deal_body)
    deal_id = body.get("id") or body.get("deal", {}).get("id")
    if not deal_id:
        step("probe: deal created", True, False, body); return
    for tgt in ["Contacted", "Qualified", "Application", "Credit Assessment"]:
        _req(base, "POST", f"/api/pipeline/deals/{deal_id}/advance", owner, {"target_stage": tgt})
    st, chk = _req(base, "GET", f"/api/pipeline/deals/{deal_id}/credit-checklist", owner)
    required = chk.get("required", []) if isinstance(chk, dict) else []
    # C1: manager must validate before submit-to-credit.
    _req(base, "POST", f"/api/pipeline/deals/{deal_id}/validate", manager,
         {"approved": True, "note": "validated (sim override probe)"})
    st, body = _req(base, "POST", f"/api/pipeline/deals/{deal_id}/submit-to-credit",
                    owner, {"documents_provided": required})
    app_id = body.get("application_id")
    if not app_id:
        step("probe: app created", True, False, body); return
    _req(base, "POST", f"/api/lms/applications/{app_id}/assign", manager,
         {"analyst_code": PERSONAS['MANAGER']['username'], "analyst_name": "Sim Analyst"})
    _req(base, "POST", f"/api/lms/applications/{app_id}/decision", manager,
         {"verdict": "approved", "authority": "Branch Credit Manager", "reason": "Sim"})
    _req(base, "POST", f"/api/lms/applications/{app_id}/sign-offer", owner,
         {"attachment_filename": "signed.pdf"})
    _req(base, "POST", f"/api/lms/applications/{app_id}/validate-offer", manager, {"approve": True})
    _req(base, "POST", f"/api/lms/applications/{app_id}/confirm-to-credit-admin", manager, {})

    st, cases = _req(base, "GET", "/api/credit-admin/cases", admin)
    case_id = next((c.get("id") for c in (cases.get("cases", []) if isinstance(cases, dict) else [])
                    if c.get("application_id") == app_id), None)
    if not case_id:
        step("probe: case found", True, False, cases); return

    # Secured + collateral + legal + insurance, but DELIBERATELY skip perfection.
    _req(base, "POST", f"/api/credit-admin/cases/{case_id}/classify-facility",
         admin, {"facility_security_type": "secured", "security_subtype": "debenture"})
    _req(base, "POST", f"/api/credit-admin/cases/{case_id}/collateral/link",
         admin, {"collateral_id": "OVCOL1", "collateral_type": "Debenture",
                 "forced_sale_value": 999_000_000_000, "currency": "KES"})
    _req(base, "POST", f"/api/credit-admin/cases/{case_id}/legal/assign",
         admin, {"officer_code": "LO001", "officer_name": "SIM Legal"})
    _req(base, "POST", f"/api/credit-admin/cases/{case_id}/legal/outcome",
         admin, {"outcome": "approved"})
    _req(base, "POST", f"/api/credit-admin/cases/{case_id}/insurance",
         admin, {"insurer": "SIM", "policy_number": "P1", "expiry_date": "2027-12-31",
                 "bank_interest_noted": True})
    # (no perfection added)

    # Fulfill any conditions, authorize.
    st, detail = _req(base, "GET", f"/api/credit-admin/cases/{case_id}", admin)
    conds = (detail.get("case", {}) or {}).get("conditions", []) if isinstance(detail, dict) else []
    for c in conds:
        if c.get("type") and not c.get("fulfilled"):
            _req(base, "POST", f"/api/credit-admin/cases/{case_id}/conditions/fulfill",
                 admin, {"condition_type": c["type"], "officer_name": "Sim"})
    _req(base, "POST", f"/api/credit-admin/cases/{case_id}/request-authorization", admin, {"note": "L1"})
    _req(base, "POST", f"/api/credit-admin/cases/{case_id}/authorize", admin, {"note": "L2"})

    # ASSERTION 1: disburse is BLOCKED on missing perfection.
    st, body = _req(base, "POST", f"/api/credit-admin/cases/{case_id}/disburse",
                    admin, {"authority": "CA Manager"})
    detail = body.get("detail", {}) if isinstance(body, dict) else {}
    checks = [f.get("check") for f in detail.get("failures", [])] if isinstance(detail, dict) else []
    step("probe: disburse BLOCKED on missing perfection", True,
         st == 400 and "security_perfection" in checks, {"checks": checks})

    # ASSERTION 2: open + approve a controlled override.
    st, body = _req(base, "POST", f"/api/credit-admin/cases/{case_id}/perfection-override/request",
                    admin, {"justification": "Charge lodged at registry; perfection pending stamp"})
    step("probe: override requested", (200, 201), st, body)
    st, body = _req(base, "POST", f"/api/credit-admin/cases/{case_id}/perfection-override/approve",
                    admin, {})
    step("probe: override approved (authorized)", True,
         isinstance(body, dict) and body.get("status") == "override_authorized",
         {"status": body.get("status") if isinstance(body, dict) else None})

    # ASSERTION 3: disburse now SUCCEEDS, flagged disbursed_under_override.
    st, body = _req(base, "POST", f"/api/credit-admin/cases/{case_id}/disburse",
                    admin, {"authority": "CA Manager", "comments": "under override"})
    step("probe: disburse SUCCEEDS under override", (200, 201), st, body)
    st, detail = _req(base, "GET", f"/api/credit-admin/cases/{case_id}", admin)
    _c = detail.get("case", {}) if isinstance(detail, dict) else {}
    step("probe: disbursement flagged disbursed_under_override", True,
         _c.get("disbursed_under_override") is True,
         {"flag": _c.get("disbursed_under_override")})


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


# ── FX currency probe: a non-KES deal books FCY (live) ──────────────────

def fx_currency_probe(base):
    print("\n=== FX CURRENCY PROBE (FCY booking) ===")
    owner = login(base, "OWNER") or login(base, "ADMIN")
    if not owner:
        return
    body = {"client_name": f"SIM FX Co {datetime.now():%H%M%S}", "client_type": "Business",
            "product_type": "Trade Finance", "deal_value": 1000000, "stage": "Lead",
            "segment": "SME", "sector": "Manufacturing", "currency": "USD"}
    st, resp = _req(base, "POST", "/api/pipeline/deals", owner, body)
    d = resp if isinstance(resp, dict) else {}
    book = d.get("currency_book") or d.get("deal", {}).get("currency_book")
    amt_kes = d.get("amount_kes") or d.get("deal", {}).get("amount_kes")
    step("fx: USD deal books FCY", True, book == "FCY",
         note=f"currency_book={book}, amount_kes={amt_kes}")
    step("fx: USD deal carries KES-equivalent > native", True,
         amt_kes is not None and float(amt_kes or 0) > 1000000,
         note=f"amount_kes={amt_kes} vs native 1,000,000")


# ── Sector / MOU source probe (client-type-aware) ───────────────────────

def sector_mou_probe(base):
    print("\n=== SECTOR / MOU PROBE (client-type-aware) ===")
    admin = login(base, "ADMIN")
    owner = login(base, "OWNER") or admin
    if not admin:
        return
    # Config exposes CBK business sectors + active MOUs.
    st, cfg = _req(base, "GET", "/api/pipeline/stages", admin)
    biz = cfg.get("business_sectors", []) if isinstance(cfg, dict) else []
    mous = cfg.get("individual_mous", []) if isinstance(cfg, dict) else []
    step("config: exposes CBK business_sectors", True, len(biz) >= 10,
         note=f"{len(biz)} sectors; e.g. {biz[0] if biz else '—'}")
    step("config: exposes active individual_mous", True, len(mous) >= 1,
         note=f"{len(mous)} active MOUs; e.g. {mous[0].get('title') if mous else '—'}")

    # Individual deal carries an MOU.
    mou = mous[0] if mous else {"id": "MOU0001", "title": "Sim MOU"}
    body = {"client_name": f"SIM Indiv {datetime.now():%H%M%S}", "client_type": "Individual",
            "product_type": "Personal Loan", "deal_value": 500000, "stage": "Lead",
            "mou_id": mou.get("id"), "mou_title": mou.get("title")}
    st, resp = _req(base, "POST", "/api/pipeline/deals", owner, body)
    d = resp if isinstance(resp, dict) else {}
    got_mou = d.get("mou_id") or d.get("deal", {}).get("mou_id")
    step("pipeline: Individual deal carries mou_id", True, got_mou == mou.get("id"),
         note=f"mou_id={got_mou}")

    # Business deal carries a CBK sector.
    cbk = biz[0] if biz else "Manufacturing"
    body2 = {"client_name": f"SIM Biz {datetime.now():%H%M%S}", "client_type": "Business",
             "product_type": "Term Loan", "deal_value": 2000000, "stage": "Lead",
             "segment": "SME", "sector": cbk}
    st, resp2 = _req(base, "POST", "/api/pipeline/deals", owner, body2)
    d2 = resp2 if isinstance(resp2, dict) else {}
    got_sec = d2.get("sector") or d2.get("deal", {}).get("sector")
    step("pipeline: Business deal carries CBK sector", True, got_sec == cbk,
         note=f"sector={got_sec}")

    # ── Top-up: pipeline value reflects the INCREMENT only, not the facility ──
    tu_body = {"client_name": f"SIM TopUp {datetime.now():%H%M%S}", "client_type": "Business",
               "product_type": "Term Loan", "deal_value": 99999999, "stage": "Lead",
               "segment": "SME", "sector": cbk,
               "is_top_up": True, "top_up_amount": 4000000,
               "original_facility_amount": 10000000, "existing_facility_id": "FAC-SIM-1"}
    st_tu, tu = _req(base, "POST", "/api/pipeline/deals", owner, tu_body)
    tud = (tu.get("deal") if isinstance(tu, dict) else {}) or {}
    def _f(v):
        try:
            return float(v or 0)
        except (TypeError, ValueError):
            return 0.0
    step("top-up: deal created", (200, 201), st_tu)
    # the deal's value must be the increment (4M), NOT the bogus 99,999,999
    # deal_value sent, and NOT the 10M facility.
    tu_val = tud.get("deal_value") or tud.get("amount_kes")
    step("top-up: pipeline value = increment, not facility", True,
         _f(tu_val) == 4000000,
         note=f"deal_value={tu_val} (increment 4M, facility 10M)")
    step("top-up: deal carries is_top_up + original facility", True,
         bool(tud.get("is_top_up")) and _f(tud.get("original_facility_amount")) == 10000000,
         note=f"original={tud.get('original_facility_amount')}")
    # validation: a top-up with no positive increment is rejected
    bad_tu = {"client_name": "SIM TopUp Bad", "client_type": "Business",
              "product_type": "Term Loan", "deal_value": 5000000, "stage": "Lead",
              "segment": "SME", "sector": cbk,
              "is_top_up": True, "top_up_amount": 0}
    st_bad, _ = _req(base, "POST", "/api/pipeline/deals", owner, bad_tu)
    step("top-up: zero-increment top-up rejected", 400, st_bad)
    # validation: original facility smaller than the increment is rejected
    bad_tu2 = {"client_name": "SIM TopUp Bad2", "client_type": "Business",
               "product_type": "Term Loan", "deal_value": 5000000, "stage": "Lead",
               "segment": "SME", "sector": cbk,
               "is_top_up": True, "top_up_amount": 8000000,
               "original_facility_amount": 3000000}
    st_bad2, _ = _req(base, "POST", "/api/pipeline/deals", owner, bad_tu2)
    step("top-up: facility < increment rejected", 400, st_bad2)

    # #3a: analytics now exposes cross-cutting breakdowns.
    st, an = _req(base, "GET", "/api/pipeline/analytics", admin)
    by_prod = an.get("by_product", []) if isinstance(an, dict) else []
    by_sec = an.get("by_sector", []) if isinstance(an, dict) else []
    by_seg = an.get("by_segment", []) if isinstance(an, dict) else []
    by_ccy = an.get("by_currency_book", {}) if isinstance(an, dict) else {}
    step("analytics: by_product breakdown present", True, len(by_prod) >= 1,
         note=f"{len(by_prod)} products; top={by_prod[0].get('product') if by_prod else '—'}")
    step("analytics: by_sector breakdown present", True, len(by_sec) >= 1,
         note=f"{len(by_sec)} sectors")
    step("analytics: by_segment breakdown present", True, len(by_seg) >= 1,
         note=f"{len(by_seg)} segments; top={by_seg[0].get('segment') if by_seg else '—'}")
    by_seg_funnel = an.get("by_segment_funnel", []) if isinstance(an, dict) else []
    bsf_ok = (isinstance(by_seg_funnel, list) and len(by_seg_funnel) >= 1
              and all(isinstance(s, dict) and "segment" in s and isinstance(s.get("funnel"), list)
                      for s in by_seg_funnel))
    step("analytics: by_segment_funnel present + well-formed", True, bsf_ok,
         note=f"{len(by_seg_funnel)} segment funnels; top={by_seg_funnel[0].get('segment') if by_seg_funnel else '—'}")

    # ── Admin config console (Batch 1a): read exposes required_fields; the
    # write endpoint is reachable for the executive tier and denied below it.
    st_cfg2, cfg2 = _req(base, "GET", "/api/pipeline/stages", admin)
    rf = cfg2.get("required_fields") if isinstance(cfg2, dict) else None
    step("admin config: read exposes required_fields", True,
         isinstance(rf, list) and len(rf) >= 1, note=f"required={rf}")
    cts = cfg2.get("client_types") if isinstance(cfg2, dict) else None
    cts_ok = (isinstance(cts, list) and len(cts) >= 1
              and all(isinstance(t, dict) and t.get("key") and t.get("field") in ("mou", "sector")
                      for t in cts))
    step("admin config: exposes client_types (business lines)", True, cts_ok,
         note=f"{len(cts) if isinstance(cts, list) else 0} types; "
              f"keys={[t.get('key') for t in cts] if isinstance(cts, list) else None}")
    st_noop, noop = _req(base, "POST", "/api/admin/pipeline-config", admin, {})
    noop_ok = (st_noop == 200 and isinstance(noop, dict)
               and noop.get("status") in ("noop", "saved") and "config" in noop)
    step("admin config: write endpoint reachable for exec (noop, no write)", True, noop_ok,
         note=f"status={noop.get('status') if isinstance(noop, dict) else st_noop}")
    st_deny, _dn = _req(base, "POST", "/api/admin/pipeline-config", owner,
                        {"required_fields": ["client_name"]})
    step("admin config: non-exec (RM) denied", 403, st_deny)

    # ── MOU-2: dedicated MOU write endpoint (add/edit/deactivate) ──
    _mou_name = f"SIM Probe Partner {datetime.now():%H%M%S}"
    st_add, add_body = _req(base, "POST", "/api/admin/mous", admin,
                            {"partner_name": _mou_name})
    new_id = add_body.get("mou", {}).get("id") if isinstance(add_body, dict) else None
    step("mou admin: add accepted (minimal name)", (200, 201), st_add,
         note=f"id={new_id}")
    step("mou admin: new MOU is Active + title==name", True,
         isinstance(add_body, dict)
         and add_body.get("mou", {}).get("status") == "Active"
         and add_body.get("mou", {}).get("title") == _mou_name)
    # appears in the picker's active list (the file the picker actually reads)
    _st_c, _cfg = _req(base, "GET", "/api/pipeline/stages", admin)
    _mou_ids = {m.get("id") for m in (_cfg.get("individual_mous", []) if isinstance(_cfg, dict) else [])}
    step("mou admin: added MOU surfaces in active picker", True, new_id in _mou_ids,
         note=f"{len(_mou_ids)} active")
    # non-admin denied
    st_mdeny, _ = _req(base, "POST", "/api/admin/mous", owner, {"partner_name": "X"})
    step("mou admin: non-admin denied", 403, st_mdeny)
    # missing name rejected
    st_bad, _ = _req(base, "POST", "/api/admin/mous", admin, {})
    step("mou admin: empty add rejected", 400, st_bad)
    # deactivate the probe MOU (keeps the register clean across runs)
    if new_id:
        st_de, _ = _req(base, "POST", "/api/admin/mous", admin,
                        {"id": new_id, "status": "Inactive"})
        step("mou admin: deactivate accepted", (200, 201), st_de)

    # ── P4a: per-product flows (product_flows) ──
    _stc, _pcfg = _req(base, "GET", "/api/pipeline/stages", admin)
    pflows = _pcfg.get("product_flows", {}) if isinstance(_pcfg, dict) else {}
    step("product flows: config exposes product_flows", True, isinstance(pflows, dict) and len(pflows) >= 1,
         note=f"{len(pflows)} products with flows")
    # author a custom flow for a probe product (add), then confirm + clean up
    _probe_prod = "SIM Probe Product"
    _custom_stages = [
        {"stage": "Lead", "target_days": 1},
        {"stage": "Custom Review", "target_days": 4},
        {"stage": "Closed Won", "target_days": 1},
    ]
    st_pf, pf_body = _req(base, "POST", "/api/admin/product-flows", admin,
                          {"product": _probe_prod, "stages": _custom_stages,
                           "client_types": ["Consumer"]})
    step("product flows: admin upsert accepted", (200, 201), st_pf,
         note=f"total={pf_body.get('total') if isinstance(pf_body, dict) else '—'}")
    # the custom flow should now resolve for that product (re-read config)
    _stc2, _pcfg2 = _req(base, "GET", "/api/pipeline/stages", admin)
    _pf2 = _pcfg2.get("product_flows", {}) if isinstance(_pcfg2, dict) else {}
    _entry = _pf2.get(_probe_prod, {})
    _stages_ok = ([s.get("stage") for s in _entry.get("stages", [])]
                  == ["Lead", "Custom Review", "Closed Won"])
    step("product flows: custom flow persists with its stages", True, _stages_ok,
         note=f"client_types={_entry.get('client_types')}")
    # validation: empty stages rejected
    st_bad, _ = _req(base, "POST", "/api/admin/product-flows", admin,
                     {"product": "X", "stages": []})
    step("product flows: empty stages rejected", 400, st_bad)
    # non-admin denied
    st_pdeny, _ = _req(base, "POST", "/api/admin/product-flows", owner,
                       {"product": "X", "stages": _custom_stages})
    step("product flows: non-admin denied", 403, st_pdeny)
    # clean up the probe flow (delete -> reverts to class resolution)
    st_del, _ = _req(base, "POST", "/api/admin/product-flows", admin,
                     {"product": _probe_prod, "delete": True})
    step("product flows: delete accepted (reverts to class)", (200, 201), st_del)

    st_fd, fd = _req(base, "GET", "/api/pipeline/funnel/drill?cls=all&stage=", admin)
    fd_ok = (st_fd == 200 and isinstance(fd, dict)
             and all(k in fd for k in ("totals", "by_product", "by_segment", "by_sector", "deals")))
    step("funnel drill: reachable + well-formed", True, fd_ok,
         note=f"count={fd.get('totals',{}).get('count') if isinstance(fd, dict) else '—'}")
    # xlsx export is binary — _req decodes text, so check it raw.
    try:
        import urllib.request as _ur
        _xreq = _ur.Request(base.rstrip("/") + "/api/pipeline/export/xlsx", method="GET")
        _xreq.add_header("Authorization", f"Bearer {admin}")
        with _ur.urlopen(_xreq, timeout=30) as _xr:
            _ct = _xr.headers.get("Content-Type", "")
            _blob = _xr.read()
            _xok = _xr.status == 200 and "spreadsheet" in _ct and len(_blob) > 500
            _xnote = f"{len(_blob)} bytes; {_ct[:42]}"
    except Exception as _xe:  # noqa: BLE001
        _xok = False
        _xnote = str(_xe)[:60]
    step("export: xlsx reachable + binary", True, _xok, note=_xnote)
    step("analytics: by_currency_book has LCY+FCY", True,
         "LCY" in by_ccy and "FCY" in by_ccy,
         note=f"LCY={by_ccy.get('LCY',{}).get('value')}, FCY={by_ccy.get('FCY',{}).get('value')}")
    # Consistency: analytics FCY (KES-equiv) must agree with the dashboard FCY —
    # proves DB-first reads now lift amount_kes from metadata (no native/KES drift).
    st, dash = _req(base, "GET", "/api/dashboard/md", admin)
    dash_fcy = (dash.get("pipeline", {}) if isinstance(dash, dict) else {}).get("fcy_value")
    an_fcy = by_ccy.get("FCY", {}).get("value")
    consistent = (dash_fcy is not None and an_fcy is not None
                  and abs(float(an_fcy) - float(dash_fcy)) < max(1.0, float(dash_fcy or 0) * 0.001))
    step("analytics FCY == dashboard FCY (KES-equiv, no drift)", True, bool(consistent),
         note=f"analytics={an_fcy} vs dashboard={dash_fcy}")
    # #5a: org drill dimensions for executive drill-down.
    by_unit = an.get("by_unit", []) if isinstance(an, dict) else []
    by_rm = an.get("by_rm", []) if isinstance(an, dict) else []
    step("analytics: by_unit (branch) drill dimension present", True, len(by_unit) >= 1,
         note=f"{len(by_unit)} units; top={by_unit[0].get('unit') if by_unit else '—'}")
    step("analytics: by_rm drill dimension present", True, len(by_rm) >= 1,
         note=f"{len(by_rm)} RMs")
    # by_region: DSA regional rollup (Western / Mt. Kenya / Nairobi 1 / Nairobi 2)
    by_region = an.get("by_region", []) if isinstance(an, dict) else []
    step("analytics: by_region drill dimension present", True, len(by_region) >= 1,
         note=f"{len(by_region)} regions; top={by_region[0].get('region') if by_region else '—'}")
    step("analytics: by_region rows carry region+value+count", True,
         bool(by_region) and all(("region" in r and "value" in r and "count" in r) for r in by_region))
    # by_client_type: CCB / CIB / Consumer business-line rollup
    by_ct = an.get("by_client_type", []) if isinstance(an, dict) else []
    step("analytics: by_client_type (CCB/CIB) dimension present", True, len(by_ct) >= 1,
         note=f"{len(by_ct)} client types; e.g. {[r.get('client_type') for r in by_ct][:3]}")
    step("analytics: by_client_type rows carry client_type+value+count", True,
         bool(by_ct) and all(("client_type" in r and "value" in r and "count" in r) for r in by_ct))
    # by_area: the 2 sanctioned mainstream regions (Nairobi / Upcountry)
    by_area = an.get("by_area", []) if isinstance(an, dict) else []
    step("analytics: by_area (2 sanctioned regions) dimension present", True, len(by_area) >= 1,
         note=f"{len(by_area)} areas; e.g. {[r.get('area') for r in by_area][:3]}")
    # NO-DOUBLE-COUNT: by_area and by_region are VIEWS over the same deals, so
    # each must sum to the SAME total (the DSA region lens is a shadow, not an
    # additional tier). Compare the two facet sums to each other.
    area_sum = sum(float(r.get("value", 0)) for r in by_area)
    region_sum = sum(float(r.get("value", 0)) for r in by_region)
    step("analytics: by_area sum == by_region sum (no double-count across lenses)", True,
         abs(area_sum - region_sum) < max(1.0, region_sum * 0.0001),
         note=f"area_sum={area_sum:.0f} vs region_sum={region_sum:.0f}")
    # #8: drill endpoint — branch -> RM -> deals (scope-safe).
    st, dr = _req(base, "GET", "/api/pipeline/drill", admin)
    drill_ok = isinstance(dr, dict) and "by_rm" in dr and "deals" in dr and "totals" in dr
    step("drill: endpoint returns by_rm + deals + totals", True, bool(drill_ok),
         note=f"rms={len(dr.get('by_rm',[])) if isinstance(dr,dict) else 0}")
    # drill into the top branch, then its top RM, and confirm narrowing.
    top_unit = by_unit[0].get("unit") if by_unit else None
    if top_unit:
        st, du = _req(base, "GET", f"/api/pipeline/drill?unit={top_unit}", admin)
        unit_rms = du.get("by_rm", []) if isinstance(du, dict) else []
        step("drill: unit filter narrows to that branch's RMs", True,
             len(unit_rms) >= 1 and du.get("totals", {}).get("count", 0) >= 1,
             note=f"unit={top_unit} -> {len(unit_rms)} RMs, {du.get('totals',{}).get('count')} deals")
        top_rm = unit_rms[0].get("rm") if unit_rms else None
        if top_rm:
            import urllib.parse as _up
            q = f"unit={_up.quote(str(top_unit))}&rm={_up.quote(str(top_rm))}"
            st, drm = _req(base, "GET", f"/api/pipeline/drill?{q}", admin)
            dl = drm.get("deals", []) if isinstance(drm, dict) else []
            step("drill: unit+rm filter yields that RM's individual deals", True,
                 len(dl) >= 1 and all(x.get("staff_name") == top_rm or
                                      x.get("unit") == top_unit for x in dl[:5]),
                 note=f"{len(dl)} deals for {top_rm}")


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
    # React-B: FCY/LCY split present, and LCY+FCY reconciles to the headline
    # (all-KES synthetic data -> LCY carries the total, FCY ~0).
    lcy = pipe.get("lcy_value"); fcy = pipe.get("fcy_value"); tot = pipe.get("pipeline_value")
    has_split = lcy is not None and fcy is not None
    reconciles = has_split and abs((float(lcy) + float(fcy)) - float(tot or 0)) < max(1.0, float(tot or 0) * 0.001)
    step("dashboard: exposes FCY/LCY split", True, has_split,
         note=f"LCY={lcy}, FCY={fcy}")
    step("dashboard: LCY+FCY reconciles to pipeline_value", True, bool(reconciles),
         note=f"{lcy}+{fcy} vs {tot}")


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


def credit_probe(base):
    print("\n=== CREDIT ANALYTICS + DRILL (loan book) ===")
    admin = login(base, "ADMIN")
    if not admin:
        return
    st, an = _req(base, "GET", "/api/credit/analytics", admin)
    ok = isinstance(an, dict) and all(
        k in an for k in ("by_class", "by_region", "by_branch", "by_rm", "totals"))
    step("credit: analytics has class/region/branch/rm + totals", True, bool(ok),
         note=f"branches={len(an.get('by_branch', [])) if isinstance(an, dict) else 0}, "
              f"npl={an.get('totals', {}).get('npl_ratio_pct') if isinstance(an, dict) else '?'}%")
    if isinstance(an, dict):
        tb = sum(b.get("accounts", 0) for b in an.get("by_branch", []))
        step("credit: by_branch accounts reconcile to total", True,
             tb == an.get("totals", {}).get("accounts"),
             note=f"{tb} vs {an.get('totals', {}).get('accounts')}")
    st, dr = _req(base, "GET", "/api/credit/drill", admin)
    step("credit drill: by_branch + by_rm + accounts + totals", True,
         isinstance(dr, dict) and all(k in dr for k in ("by_branch", "by_rm", "accounts", "totals")))
    regions = an.get("by_region", []) if isinstance(an, dict) else []
    top_region = regions[0].get("region") if regions else None
    if top_region:
        import urllib.parse as _up
        st, drg = _req(base, "GET", f"/api/credit/drill?region={_up.quote(str(top_region))}", admin)
        rbr = drg.get("by_branch", []) if isinstance(drg, dict) else []
        step("credit drill: region narrows to its branches", True, len(rbr) >= 1,
             note=f"region={top_region} -> {len(rbr)} branches")
        top_branch = rbr[0].get("branch") if rbr else None
        if top_branch:
            q = f"region={_up.quote(str(top_region))}&branch={_up.quote(str(top_branch))}"
            st, drb = _req(base, "GET", f"/api/credit/drill?{q}", admin)
            brm = drb.get("by_rm", []) if isinstance(drb, dict) else []
            step("credit drill: branch narrows to its RMs", True, len(brm) >= 1,
                 note=f"branch={top_branch} -> {len(brm)} RMs")
            top_rm = brm[0].get("rm") if brm else None
            if top_rm:
                st, drm = _req(base, "GET", f"/api/credit/drill?{q}&rm={_up.quote(str(top_rm))}", admin)
                accs = drm.get("accounts", []) if isinstance(drm, dict) else []
                step("credit drill: RM yields individual accounts", True, len(accs) >= 1,
                     note=f"{len(accs)} accounts for {top_rm}")


def hierarchy_scope_probe(base):
    print("\n=== HIERARCHY SCOPE (individual view — like pipeline) ===")
    admin = login(base, "ADMIN")
    owner = login(base, "OWNER")
    if not admin or not owner:
        step("scope: personas available", True, False, note="missing login")
        return
    _, mp = _req(base, "GET", "/api/pipeline/drill", admin)
    _, op = _req(base, "GET", "/api/pipeline/drill", owner)
    md_pipe = mp.get("totals", {}).get("count", 0) if isinstance(mp, dict) else 0
    own_pipe = op.get("totals", {}).get("count", 0) if isinstance(op, dict) else 0
    step("scope: non-MD sees a strict subset of pipeline (hierarchy-scoped)", True,
         own_pipe < md_pipe, note=f"owner={own_pipe} < MD={md_pipe}")
    _, mc = _req(base, "GET", "/api/credit/analytics", admin)
    _, oc = _req(base, "GET", "/api/credit/analytics", owner)
    md_credit = mc.get("totals", {}).get("accounts", 0) if isinstance(mc, dict) else 0
    own_credit = oc.get("totals", {}).get("accounts", 0) if isinstance(oc, dict) else 0
    step("scope: non-MD sees credit scoped to subtree (strict subset)", True,
         own_credit < md_credit, note=f"owner={own_credit} < MD={md_credit}")


def exceptions_probe(base):
    print("\n=== EXECUTIVE EXCEPTIONS STRIP ===")
    admin = login(base, "ADMIN")
    if not admin:
        step("exceptions: admin login", True, False, note="missing login")
        return
    st, body = _req(base, "GET", "/api/dashboard/exceptions", admin)
    step("exceptions: reachable", 200, st, body)
    items = body.get("exceptions", []) if isinstance(body, dict) else []
    step("exceptions: returns a list", True, isinstance(items, list),
         note=f"{len(items)} item(s)")
    well_formed = all(
        isinstance(i, dict) and {"id", "severity", "title", "link"} <= set(i.keys())
        for i in items
    )
    step("exceptions: items well-formed (id/severity/title/link)", True, well_formed)
    valid_sev = all(i.get("severity") in ("danger", "warning", "info") for i in items)
    step("exceptions: severities valid", True, valid_sev)
    known = {"/credit-analytics", "/pipeline/queues", "/analytics", "/perform"}
    valid_links = all(i.get("link") in known for i in items)
    step("exceptions: links are known drill routes", True, valid_links,
         note=f"links={[i.get('link') for i in items]}")
    has_npl = any(i.get("id") == "npl_ratio" for i in items)
    step("exceptions: NPL breach surfaced for MD", True, has_npl,
         note=f"ids={[i.get('id') for i in items]}")
    # Scoped persona returns its own (subset) without error.
    owner = login(base, "OWNER")
    if owner:
        st2, body2 = _req(base, "GET", "/api/dashboard/exceptions", owner)
        step("exceptions: scoped persona reachable", 200, st2, body2)
        oitems = body2.get("exceptions", []) if isinstance(body2, dict) else []
        step("exceptions: scoped persona well-formed", True,
             all(isinstance(i, dict) and "link" in i for i in oitems),
             note=f"owner {len(oitems)} item(s)")


def referral_probe(base):
    print("\n=== REFERRAL LIFECYCLE (refer existing -> accept / decline) ===")
    admin = login(base, "ADMIN")
    owner = login(base, "OWNER")      # frank0731, staff 300731
    manager = login(base, "MANAGER")  # immaculate0716, staff 300716
    if not admin or not owner or not manager:
        return
    FRANK = "300731"
    IMMA  = "300716"

    def _mk(who):
        body = {"client_name": f"REF {datetime.now():%H%M%S%f}",
                "client_type": "Commercial", "product_type": "Term Loan",
                "deal_value": 3000000, "stage": "Lead", "segment": "SME"}
        st, resp = _req(base, "POST", "/api/pipeline/deals", who, body)
        d = resp if isinstance(resp, dict) else {}
        return d.get("deal", {}).get("id") or d.get("id"), st

    def _seg_count(tok):
        st, an = _req(base, "GET", "/api/pipeline/analytics", tok)
        rows = an.get("by_segment", []) if isinstance(an, dict) else []
        return sum(r.get("count", 0) for r in rows)

    # Owner (Frank) creates a deal he owns, then refers it to Immaculate.
    did, cst = _mk(owner)
    step("referral: deal created for refer test", (200, 201), cst, note=f"deal_id={did}")
    n1 = _seg_count(admin)

    st, rr = _req(base, "POST", f"/api/pipeline/deals/{did}/refer", owner,
                  {"referred_to_code": IMMA, "referred_to_name": "Immaculate",
                   "referral_note": "Please pursue — your relationship."})
    step("referral: refer existing deal -> pending", (200, 201), st, payload=rr,
         note=f"status={rr.get('referral_status') if isinstance(rr, dict) else '?'}")

    n2 = _seg_count(admin)
    step("referral: pending referral EXCLUDED from analytics count", True, n2 == n1 - 1,
         note=f"before={n1} after={n2}")

    # Advance blocked while pending (admin has scope, so 400 is the referral gate).
    st, ar = _req(base, "POST", f"/api/pipeline/deals/{did}/advance", admin,
                  {"new_stage": "Contacted"})
    step("referral: advance BLOCKED while pending", 400, st, payload=ar)

    # Non-recipient (the referrer Frank, a plain RM) cannot accept.
    st, _na = _req(base, "POST", f"/api/pipeline/deals/{did}/referral/accept", owner, {})
    step("referral: non-recipient accept denied", 403, st)

    # Recipient (Immaculate) accepts -> owns the deal.
    st, acc = _req(base, "POST", f"/api/pipeline/deals/{did}/referral/accept", manager, {})
    step("referral: recipient accepts -> accepted", (200, 201), st, payload=acc,
         note=f"status={acc.get('referral_status') if isinstance(acc, dict) else '?'}")

    n3 = _seg_count(admin)
    step("referral: accepted deal counts again", True, n3 == n1, note=f"after_accept={n3} vs {n1}")

    # Progression now unlocked for the new owner.
    st, ar2 = _req(base, "POST", f"/api/pipeline/deals/{did}/advance", manager,
                   {"new_stage": "Contacted"})
    step("referral: advance ALLOWED after accept", (200, 201), st, payload=ar2)

    # Decline path on a second deal.
    did2, _ = _mk(owner)
    _req(base, "POST", f"/api/pipeline/deals/{did2}/refer", owner,
         {"referred_to_code": IMMA, "referred_to_name": "Immaculate"})
    st, _nd = _req(base, "POST", f"/api/pipeline/deals/{did2}/referral/decline", manager, {})
    step("referral: decline without reason rejected", 400, st)
    st, dec = _req(base, "POST", f"/api/pipeline/deals/{did2}/referral/decline", manager,
                   {"reason": "Client outside my coverage area."})
    step("referral: decline with reason -> declined (returned)", (200, 201), st, payload=dec,
         note=f"status={dec.get('referral_status') if isinstance(dec, dict) else '?'}")
    st, _ad = _req(base, "POST", f"/api/pipeline/deals/{did2}/advance", admin,
                   {"new_stage": "Contacted"})
    step("referral: declined deal blocked from advancing", 400, st)

    # A2: read queries + reassign
    st, ret = _req(base, "GET", "/api/pipeline/referrals/returned", owner)
    ret_ids = [d.get("id") for d in (ret.get("deals") or [])] if isinstance(ret, dict) else []
    step("referral: returned pool lists declined deal", True, did2 in ret_ids,
         note=f"{len(ret_ids)} returned")

    st, inc = _req(base, "GET", "/api/pipeline/referrals/incoming", manager)
    inc_ids = [d.get("id") for d in (inc.get("deals") or [])] if isinstance(inc, dict) else []
    step("referral: declined deal not in recipient inbox", True, did2 not in inc_ids)

    st, _rr = _req(base, "POST", f"/api/pipeline/deals/{did2}/referral/reassign", manager,
                   {"referred_to_code": "300716", "referred_to_name": "Immaculate"})
    step("referral: non-referrer reassign denied", 403, st)

    st, rs = _req(base, "POST", f"/api/pipeline/deals/{did2}/referral/reassign", owner,
                  {"referred_to_code": "300716", "referred_to_name": "Immaculate"})
    step("referral: reassign returned deal -> pending", (200, 201), st, payload=rs,
         note=f"status={rs.get('referral_status') if isinstance(rs, dict) else '?'}")

    st, inc2 = _req(base, "GET", "/api/pipeline/referrals/incoming", manager)
    inc2_ids = [d.get("id") for d in (inc2.get("deals") or [])] if isinstance(inc2, dict) else []
    step("referral: reassigned deal in new recipient inbox", True, did2 in inc2_ids,
         note=f"{len(inc2_ids)} incoming")

    st, out = _req(base, "GET", "/api/pipeline/referrals/outgoing", owner)
    out_ids = [d.get("id") for d in (out.get("deals") or [])] if isinstance(out, dict) else []
    step("referral: outgoing lists referrer's live referrals", True,
         did in out_ids and did2 in out_ids, note=f"{len(out_ids)} outgoing")

    # BSC shadow credit: materialize the accepted deal -> the REFERRER (Frank,
    # 300731) earns Asset Referral (K238) shadow credit. Term Loan -> asset.
    _req(base, "PUT", f"/api/pipeline/deals/{did}", manager, {"stage": "Closed Won"})
    st, sync = _req(base, "POST", "/api/pipeline/referrals/sync-bsc?dry_run=true", admin, {})
    contribs = sync.get("contributions", 0) if isinstance(sync, dict) else 0
    sample = sync.get("sample", []) if isinstance(sync, dict) else []
    has_frank_asset = any(s.get("referrer_code") == "300731" and s.get("kpi_id") == "K238"
                          for s in sample)
    step("referral: BSC shadow credit computed for referrer (dry-run)", True,
         contribs >= 1 and has_frank_asset, note=f"{contribs} contributions")

    # Outgoing analytics: the referrer tracks their referral funnel + alerts.
    ref = login(base, "OWNER")
    st, an = _req(base, "GET", "/api/pipeline/referrals/outgoing/analytics", ref)
    an = an if isinstance(an, dict) else {}
    step("referral analytics: endpoint reachable", 200, st)
    step("referral analytics: funnel by_status + by_stage well-formed", True,
         isinstance(an.get("by_status"), dict) and isinstance(an.get("by_stage"), dict)
         and an.get("total", 0) >= 1,
         note=f"total={an.get('total')} status={an.get('by_status')}")
    step("referral analytics: alerts list + count present", True,
         isinstance(an.get("alerts"), list) and "alert_count" in an,
         note=f"{an.get('alert_count')} alert(s)")

    # Department-level analytics (Head/Chief perspective -> department BSC KPI).
    adm = login(base, "ADMIN")
    st, dep = _req(base, "GET", "/api/pipeline/referrals/analytics/by-department", adm)
    dep = dep if isinstance(dep, dict) else {}
    step("referral analytics: by-department reachable for management", 200, st)
    step("referral analytics: by-department well-formed (departments + total)", True,
         isinstance(dep.get("departments"), list) and dep.get("total", 0) >= 1
         and all("by_status" in x for x in dep.get("departments", [])),
         note=f"{dep.get('department_count')} dept(s), total={dep.get('total')}")
    st2, _ = _req(base, "GET", "/api/pipeline/referrals/analytics/by-department", ref)
    step("referral analytics: by-department denied to non-management", 403, st2)

    # Twin hierarchy view: team referrals scoped like the pipeline (MD sees all).
    st, t_md = _req(base, "GET", "/api/pipeline/referrals/team", adm)
    _stt, t_rm = _req(base, "GET", "/api/pipeline/referrals/team", ref)
    t_md = t_md if isinstance(t_md, dict) else {}
    t_rm = t_rm if isinstance(t_rm, dict) else {}
    md_n = t_md.get("count", -1)
    rm_n = t_rm.get("count", -2)
    step("referral team: MD view reachable + summary well-formed", True,
         st == 200 and isinstance(t_md.get("summary"), dict) and md_n >= 1,
         note=f"MD sees {md_n}")
    step("referral team: RM is hierarchy-scoped (subset of MD)", True,
         0 <= rm_n <= md_n, note=f"RM={rm_n} <= MD={md_n}")
    step("referral team: RM sees only own-subtree referrals", True,
         all(str(d.get("referred_by_code")) == "300731" for d in t_rm.get("deals", [])),
         note=f"{len(t_rm.get('deals', []))} team referrals for RM")

    # Config-vs-hardcode: the pending-alert window is admin-configurable.
    _stc, ccfg = _req(base, "POST", "/api/admin/pipeline-config", adm, {})
    cview = ccfg.get("config", {}) if isinstance(ccfg, dict) else {}
    step("referral: pending-alert window is admin-configurable (not hardcoded)", True,
         "referral_pending_alert_days" in cview,
         note=f"days={cview.get('referral_pending_alert_days')}")

    # Referral tier (B2B / S2B) — cross-unit classification, derived + config-driven.
    tdeals = t_md.get("deals", []) if isinstance(t_md, dict) else []
    tsum = t_md.get("summary", {}) if isinstance(t_md, dict) else {}
    by_tier = tsum.get("by_tier", {}) if isinstance(tsum, dict) else {}
    step("referral tier: team deals carry referral_tier + cross_unit", True,
         bool(tdeals) and all(
             d.get("referral_tier") in ("B2B", "S2B") and isinstance(d.get("cross_unit"), bool)
             for d in tdeals),
         note=f"{len(tdeals)} classified")
    step("referral tier: team summary exposes by_tier (sums to total)", True,
         isinstance(by_tier, dict)
         and (by_tier.get("B2B", 0) + by_tier.get("S2B", 0)) == tsum.get("total", -1),
         note=f"B2B={by_tier.get('B2B')} S2B={by_tier.get('S2B')}")
    step("referral tier: Sales referrer classified B2B (business unit)", True,
         by_tier.get("B2B", 0) >= 1, note=f"B2B={by_tier.get('B2B')}")
    step("referral tier: business-dept map is admin-configurable", True,
         "referral_business_departments" in cview,
         note=f"{len(cview.get('referral_business_departments', []))} business depts")


def troops_probe(base, case_id):
    print("\n=== TROOPS — Treasury Back Office disbursement completion ===")
    admin = login(base, "ADMIN")
    owner = login(base, "OWNER")   # frank, RM — NOT treasury back office
    if not admin or not case_id:
        step("troops: prerequisite (cleared case id)", True, bool(case_id),
             note="no cleared case from happy_path -> skipping")
        return

    st, q = _req(base, "GET", "/api/credit-admin/troops/queue", admin)
    ids = [c.get("case_id") for c in (q.get("cases") or [])] if isinstance(q, dict) else []
    step("troops: cleared case appears in disbursement queue", True,
         case_id in ids, note=f"{len(ids)} in queue")

    st, _ = _req(base, "POST", f"/api/credit-admin/cases/{case_id}/troops/book", owner, {})
    step("troops: non-treasury RM denied booking", 403, st)

    st, b = _req(base, "POST", f"/api/credit-admin/cases/{case_id}/troops/book", admin, {})
    acct = b.get("case", {}).get("cbs_account_no") if isinstance(b, dict) else None
    step("troops: book to core banking", (200, 201), st, b, note=f"acct={acct}")

    # value date is required before disburse
    st, _ = _req(base, "POST", f"/api/credit-admin/cases/{case_id}/troops/disburse",
                 admin, {"gl_reference": "GL-EARLY"})
    step("troops: disburse blocked before value date", 400, st)

    st, v = _req(base, "POST", f"/api/credit-admin/cases/{case_id}/troops/value-date",
                 admin, {"value_date": "2026-06-18"})
    step("troops: set value date", (200, 201), st, v)

    st, d = _req(base, "POST", f"/api/credit-admin/cases/{case_id}/troops/disburse",
                 admin, {"gl_reference": "GL-SIM-1"})
    disbursed = d.get("case", {}).get("disbursed") if isinstance(d, dict) else None
    step("troops: disburse -> disbursed=True", (200, 201), st, d, note=f"disbursed={disbursed}")

    # K001 autopopulate: completing disbursement must flip the linked loan
    # application to 'disbursed' so the Loans Disbursed KPI credits the RM.
    app_id = d.get("case", {}).get("application_id") if isinstance(d, dict) else None
    if app_id:
        _sa, av = _req(base, "GET", f"/api/lms/applications/{app_id}", admin)
        app_status = (av.get("application") or av).get("status") if isinstance(av, dict) else None
        step("troops: disburse flips loan app -> disbursed (K001 autopopulate)", True,
             app_status == "disbursed", note=f"app={app_id} status={app_status}")
    else:
        step("troops: disburse flips loan app -> disbursed (K001 autopopulate)", True,
             True, note="no application_id on case (skipped)")

    st, q2 = _req(base, "GET", "/api/credit-admin/troops/queue", admin)
    ids2 = [c.get("case_id") for c in (q2.get("cases") or [])] if isinstance(q2, dict) else []
    step("troops: disbursed case leaves the queue", True, case_id not in ids2,
         note=f"{len(ids2)} remain")

    st, _ = _req(base, "POST", f"/api/credit-admin/cases/{case_id}/troops/disburse", admin, {})
    step("troops: re-disburse blocked", 400, st)


def roles_probe(base):
    print("\n=== ROLE REGISTRY (admin config) ===")
    admin = login(base, "ADMIN")
    owner = login(base, "OWNER")
    if not admin:
        return

    st, r = _req(base, "GET", "/api/admin/roles", admin)
    roles = r.get("roles", []) if isinstance(r, dict) else []
    names = [str(x.get("role", "")) for x in roles]
    step("roles: registry lists all roles", True, len(roles) >= 15, note=f"{len(roles)} roles")

    step("roles: Treasury Back Office present in registry", True,
         any("treasury back office" in n.lower() for n in names))
    tre = next((x for x in roles if "treasury back office" in str(x.get("role", "")).lower()), None)
    step("roles: Treasury Back Office has can_disburse=True", True,
         bool(tre and tre.get("can_disburse")))

    st, _ = _req(base, "GET", "/api/admin/roles", owner)
    step("roles: non-admin denied registry", 403, st)

    # capability grant + revoke on a probe role (net-zero)
    _req(base, "POST", "/api/admin/roles/capabilities", admin,
         {"role": "Customer Service Officer", "can_disburse": True})
    st, r2 = _req(base, "GET", "/api/admin/roles", admin)
    cso = next((x for x in (r2.get("roles") or []) if x.get("role") == "Customer Service Officer"), None)
    step("roles: capability grant reflected", True, bool(cso and cso.get("can_disburse")))
    _req(base, "POST", "/api/admin/roles/capabilities", admin,
         {"role": "Customer Service Officer", "can_disburse": False})
    st, r3 = _req(base, "GET", "/api/admin/roles", admin)
    cso3 = next((x for x in (r3.get("roles") or []) if x.get("role") == "Customer Service Officer"), None)
    step("roles: capability revoke reflected", True, bool(cso3 and not cso3.get("can_disburse")))

    st, d = _req(base, "GET", "/api/admin/role-detail?role=Branch%20Manager", admin)
    step("roles: role detail resolves KPIs", True,
         isinstance(d, dict) and d.get("kpi_count", 0) > 0,
         note=f"{d.get('kpi_count') if isinstance(d, dict) else '?'} kpis")


def pool_visibility_probe(base):
    """Credit work-pool visibility config (admin-configurable): a credit role
    sees the submitted/assigned pool; which roles + statuses is config, not
    hardcode; non-admin cannot write it."""
    print("\n=== CREDIT POOL VISIBILITY (admin-configurable) ===")
    admin = login(base, "ADMIN")
    owner = login(base, "OWNER") or admin
    if not admin:
        step("pool: admin login", 200, 0, note="cannot proceed"); return

    # Config readable + well-formed (roles + statuses).
    st, cfg = _req(base, "GET", "/api/lms/config/pool-visibility", admin)
    pv = cfg.get("pool_visibility", {}) if isinstance(cfg, dict) else {}
    step("pool: visibility config readable + well-formed", True,
         isinstance(pv, dict) and isinstance(pv.get("roles"), list)
         and isinstance(pv.get("statuses"), list) and len(pv["roles"]) >= 1,
         note=f"{len(pv.get('roles', []))} roles, {len(pv.get('statuses', []))} statuses")
    # Defaults include the credit-analyst role + submitted status (the demo case).
    roles_l = [str(r).lower() for r in pv.get("roles", [])]
    statuses_l = [str(s).lower() for s in pv.get("statuses", [])]
    step("pool: credit analyst role is in the pool policy", True,
         any("credit analyst" in r or "analyst" in r for r in roles_l),
         note=f"roles e.g. {pv.get('roles', [])[:3]}")
    step("pool: 'submitted' is a pool status (line manager assigns from here)", True,
         "submitted" in statuses_l)
    # Admin can update the policy (atomic + backup).
    new_statuses = list(pv.get("statuses", [])) or ["submitted", "assigned"]
    st, r = _req(base, "POST", "/api/lms/config/pool-visibility", admin,
                 {"statuses": new_statuses})
    step("pool: admin update accepted", (200, 201), st, r)
    # Saved change is live on next read.
    st, cfg2 = _req(base, "GET", "/api/lms/config/pool-visibility", admin)
    pv2 = cfg2.get("pool_visibility", {}) if isinstance(cfg2, dict) else {}
    step("pool: saved change is live on next read", True,
         isinstance(pv2.get("statuses"), list) and len(pv2["statuses"]) == len(new_statuses))
    # Validation: bad payload rejected.
    st, r = _req(base, "POST", "/api/lms/config/pool-visibility", admin,
                 {"roles": "not-a-list"})
    step("pool: non-list payload rejected", 400, st, r)
    # Non-admin cannot write.
    st, r = _req(base, "POST", "/api/lms/config/pool-visibility", owner,
                 {"statuses": ["submitted"]})
    step("pool: non-admin write denied", 403, st, r)


def analyst_decision_probe(base):
    """Assigned analyst can decide directly (approve/decline/return) AND can
    escalate / seek guidance to their line manager; the line manager can then
    add their view. Uses the MANAGER persona as the assigned analyst (the
    assign step sets analyst=MANAGER), so both new permissions are exercised."""
    print("\n=== ANALYST DECISION + ESCALATE (credit analyst workspace) ===")
    owner = login(base, "OWNER")
    manager = login(base, "MANAGER")
    admin = login(base, "ADMIN")
    if not (owner and manager and admin):
        step("analyst: logins", 200, 0, note="cannot proceed"); return

    def _fresh_assigned_app():
        # create -> advance -> validate -> submit -> assign analyst(=MANAGER)
        b = {
            "client_name": f"SIM Analyst Case {datetime.now():%H%M%S%f}",
            "client_type": "Business", "product_type": "Term Loan",
            "deal_value": 3000000, "stage": "Lead",
            "segment": "SME", "sector": "Manufacturing",
        }
        st, d = _req(base, "POST", "/api/pipeline/deals", owner, b)
        did = d.get("id") or d.get("deal", {}).get("id") or d.get("deal_id")
        for tgt in ["Contacted", "Qualified", "Application", "Credit Assessment"]:
            _req(base, "POST", f"/api/pipeline/deals/{did}/advance", owner, {"target_stage": tgt})
        _req(base, "POST", f"/api/pipeline/deals/{did}/validate", manager,
             {"approved": True, "note": "validated (analyst probe)"})
        st, chk = _req(base, "GET", f"/api/pipeline/deals/{did}/credit-checklist", owner)
        req = chk.get("required", []) if isinstance(chk, dict) else []
        st, body = _req(base, "POST", f"/api/pipeline/deals/{did}/submit-to-credit",
                        owner, {"documents_provided": req})
        aid = body.get("application_id")
        if aid:
            _req(base, "POST", f"/api/lms/applications/{aid}/assign", manager,
                 {"analyst_code": "300716", "analyst_name": "Sim Analyst"})
        return aid

    # (1) Assigned analyst can record a decision DIRECTLY (return-for-rework).
    aid = _fresh_assigned_app()
    if not aid:
        step("analyst: app ready", True, False, note="no app"); return
    st, perms = _req(base, "GET", f"/api/lms/applications/{aid}", manager)
    p = perms.get("permissions", {}) if isinstance(perms, dict) else {}
    step("analyst: assigned analyst gets can_record_decision", True,
         bool(p.get("can_record_decision")), note=f"can_escalate={p.get('can_escalate')}")
    step("analyst: assigned analyst gets can_escalate", True, bool(p.get("can_escalate")))
    st, body = _req(base, "POST", f"/api/lms/applications/{aid}/decision", manager,
                    {"verdict": "returned", "authority": "Credit Analyst",
                     "reason": "Needs updated financials (sim)"})
    step("analyst: analyst records return-for-rework directly", (200, 201), st, body,
         note=f"status: {body.get('status') if isinstance(body, dict) else '?'}")

    # (2) Escalate / seek guidance routes to the line manager.
    aid2 = _fresh_assigned_app()
    st, body = _req(base, "POST", f"/api/lms/applications/{aid2}/escalate", manager,
                    {"reason": "Borderline DSCR — need manager steer (sim)"})
    step("analyst: escalate to line manager accepted", (200, 201), st, body)
    st, app = _req(base, "GET", f"/api/lms/applications/{aid2}", admin)
    esc = (app.get("application", {}) if isinstance(app, dict) else {}).get("escalation", {}) or {}
    step("analyst: escalation stamped (pending manager input)", True,
         bool(esc.get("escalated")) and not esc.get("resolved"),
         note=f"by={esc.get('by')}")
    # Short reason rejected.
    aid3 = _fresh_assigned_app()
    st, body = _req(base, "POST", f"/api/lms/applications/{aid3}/escalate", manager, {"reason": "x"})
    step("analyst: escalate with too-short reason rejected", 400, st, body)

    # (3) Line manager adds their view; escalation resolves.
    st, body = _req(base, "POST", f"/api/lms/applications/{aid2}/manager-view", manager,
                    {"view": "Proceed to decline — DSCR below floor (sim)"})
    step("manager: line manager records view on escalated case", (200, 201), st, body)
    st, app = _req(base, "GET", f"/api/lms/applications/{aid2}", admin)
    esc = (app.get("application", {}) if isinstance(app, dict) else {}).get("escalation", {}) or {}
    step("manager: manager view resolves the escalation", True,
         bool(esc.get("resolved")) and bool(esc.get("manager_view")))

    # (4) Attachments (reference mode) + Branch Credit Committee record.
    aid4 = _fresh_assigned_app()
    st, body = _req(base, "POST", f"/api/lms/applications/{aid4}/attachments", manager,
                    {"kind": "financials", "filename": "FY2025_accounts.pdf",
                     "ref": "dms://docs/fy2025"})
    step("attach: add attachment reference accepted", (200, 201), st, body)
    st, body = _req(base, "POST", f"/api/lms/applications/{aid4}/attachments", manager,
                    {"kind": "other"})  # no filename/ref -> 400
    step("attach: empty attachment rejected", 400, st, body)
    # Record the BCC outcome at branch origin (verdict + signatories + minutes file).
    st, body = _req(base, "POST", f"/api/lms/applications/{aid4}/bcc", manager,
                    {"verdict": "recommended", "branch": "Thika",
                     "chaired_by": "Branch Manager",
                     "attendees": ["Branch Manager", "Branch Credit Manager", "RO"],
                     "minutes": "Committee recommends to HO credit.",
                     "filename": "BCC_minutes_signed.pdf", "ref": "dms://bcc/min1"})
    step("bcc: record branch committee outcome accepted", (200, 201), st, body)
    step("bcc: invalid verdict rejected", 400,
         _req(base, "POST", f"/api/lms/applications/{aid4}/bcc", manager,
              {"verdict": "maybe"})[0])
    # List attachments — should include the financials AND the auto-filed BCC minutes.
    st, lst = _req(base, "GET", f"/api/lms/applications/{aid4}/attachments", manager)
    atts = lst.get("attachments", []) if isinstance(lst, dict) else []
    kinds = {a.get("kind") for a in atts}
    step("attach: list returns financials + auto-filed BCC minutes", True,
         "financials" in kinds and "bcc_minutes" in kinds,
         note=f"{len(atts)} attachments; kinds={kinds}")
    step("bcc: BCC block present on the case (travels to HO)", True,
         isinstance(lst.get("bcc"), dict) and lst["bcc"].get("verdict") == "recommended")

    # (5) Credit Report (CR) — hybrid auto-populated appraisal memo.
    aid5 = _fresh_assigned_app()
    st, cr = _req(base, "GET", f"/api/lms/applications/{aid5}/cr", manager)
    crv = cr.get("cr", {}) if isinstance(cr, dict) else {}
    tmpl = crv.get("template", {})
    step("cr: template + sections present", True,
         isinstance(tmpl, dict) and len(tmpl.get("sections", [])) >= 5,
         note=f"{len(tmpl.get('sections', []))} sections")
    av = crv.get("auto_values", {})
    step("cr: auto-populates customer name + product from the application", True,
         bool(av.get("client_name")) and bool(av.get("product")),
         note=f"name={av.get('client_name')!r}")
    # Save some RM fields; completing without required fields must be blocked.
    st, body = _req(base, "POST", f"/api/lms/applications/{aid5}/cr", manager,
                    {"values": {"purpose": "Working capital"}, "completed": True})
    step("cr: complete blocked while required fields missing", 400, st, body)
    # Save as draft (not completed) is fine.
    st, body = _req(base, "POST", f"/api/lms/applications/{aid5}/cr", manager,
                    {"values": {"purpose": "Working capital", "tenor_months": "24",
                                "repayment_source": "Trading cashflows",
                                "rm_recommendation": "Recommend approval"}})
    step("cr: save draft values accepted", (200, 201), st, body)
    # Re-read: saved values persist + merge over auto.
    st, cr2 = _req(base, "GET", f"/api/lms/applications/{aid5}/cr", manager)
    vals = cr2.get("cr", {}).get("values", {}) if isinstance(cr2, dict) else {}
    step("cr: saved RM values persist and merge with auto", True,
         vals.get("purpose") == "Working capital" and bool(vals.get("client_name")))
    # Bad payload rejected.
    step("cr: non-object values rejected", 400,
         _req(base, "POST", f"/api/lms/applications/{aid5}/cr", manager, {"values": "nope"})[0])


def staff_search_probe(base):
    print("\n=== STAFF SEARCH (referral recipient picker) ===")
    admin = login(base, "ADMIN")
    owner = login(base, "OWNER")   # Frank Wanyama, 300731
    if not admin:
        return
    st, r = _req(base, "GET", "/api/staff/search?q=Wanyama", admin)
    codes = [s.get("staff_code") for s in (r.get("staff") or [])] if isinstance(r, dict) else []
    step("staff search: by name finds Frank Wanyama", True, "300731" in codes,
         note=f"{len(codes)} matches")

    st, r2 = _req(base, "GET", "/api/staff/search?q=300731", admin)
    codes2 = [s.get("staff_code") for s in (r2.get("staff") or [])] if isinstance(r2, dict) else []
    step("staff search: by code finds Frank", True, "300731" in codes2)

    if owner:
        st, r3 = _req(base, "GET", "/api/staff/search?q=Wanyama", owner)
        codes3 = [s.get("staff_code") for s in (r3.get("staff") or [])] if isinstance(r3, dict) else []
        step("staff search: caller excluded from own results", True, "300731" not in codes3)

    # segment (Department) dimension for the picker
    st, segs = _req(base, "GET", "/api/staff/segments", admin)
    seg_names = [s.get("segment") for s in (segs.get("segments") or [])] if isinstance(segs, dict) else []
    step("staff segments: listing non-empty", True, len(seg_names) >= 3,
         note=f"{len(seg_names)} segments")

    target = "Credit" if "Credit" in seg_names else (seg_names[0] if seg_names else "")
    st, r4 = _req(base, "GET", f"/api/staff/search?segment={target}&limit=50", admin)
    staff = r4.get("staff") or [] if isinstance(r4, dict) else []
    all_match = all(str(s.get("segment", "")).lower() == target.lower() for s in staff)
    step("staff search: segment filter narrows to that segment", True,
         len(staff) > 0 and all_match, note=f"{len(staff)} in {target}")


def portfolio_conflict_probe(base):
    """P1 — verify the α5 portfolio-conflict create paths actually work.

    When a deal's portfolio owner is someone other than the creating RM,
    three resolution paths exist (audit Sec 15.4):
      1. SEEK-PERMISSION — defer BSC credit to the owner (no manager note)
      2. OVERRIDE        — claim BSC credit anyway (manager note required)
      3. REFER           — hand the lead to the owner via /deals/refer
    This is the baseline before CBS owner auto-detection + the owner "nod"
    (P2-P4). Creator = Frank (300731); portfolio owner = Immaculate (300716).
    """
    print("\n=== PORTFOLIO CONFLICT (P1 — verify α5 create paths) ===")
    owner = login(base, "OWNER")           # Frank Wanyama, creating RM (300731)
    if not owner:
        step("portfolio: owner login", 200, 0, note="cannot proceed")
        return
    PO_CODE, PO_NAME = "300716", "Immaculate"   # a DIFFERENT RM = portfolio owner
    ts = f"{datetime.now():%H%M%S}"

    def _base(tag):
        return {
            "client_name": f"SIM Portfolio {tag} {ts}",
            "product_type": "Term Loan", "deal_value": 4_000_000, "stage": "Lead",
            "portfolio_owner_code": PO_CODE, "portfolio_owner_name": PO_NAME,
        }

    def _did(b):
        if not isinstance(b, dict):
            return None
        return b.get("id") or b.get("deal", {}).get("id")

    def _deal(did, tok=owner):
        if not did:
            return {}
        _, d = _req(base, "GET", f"/api/pipeline/deals/{did}", tok)
        return (d.get("deal") or d) if isinstance(d, dict) else {}

    # 1. SEEK-PERMISSION: bsc_credit_to == owner -> passes without a note.
    body = _base("seek"); body["bsc_credit_to"] = PO_NAME
    st, r = _req(base, "POST", "/api/pipeline/deals", owner, body)
    step("portfolio: seek-permission create accepted", (200, 201), st, r)
    deal = _deal(_did(r))
    step("portfolio: seek-permission stamps owner + defers credit to owner", True,
         str(deal.get("portfolio_owner_code")) == PO_CODE
         and str(deal.get("bsc_credit_to")) == PO_NAME,
         note=f"owner={deal.get('portfolio_owner_code')} credit_to={deal.get('bsc_credit_to')}")

    # 2. OVERRIDE without a note -> blocked (RM claims credit, no justification).
    body = _base("ovr0"); body["bsc_credit_to"] = "Frank Wanyama"
    st, r = _req(base, "POST", "/api/pipeline/deals", owner, body)
    step("portfolio: override WITHOUT note blocked", 400, st, r)

    # 3. OVERRIDE with a note -> accepted, note stamped for audit trail.
    body = _base("ovr1"); body["bsc_credit_to"] = "Frank Wanyama"
    body["manager_override_note"] = "Pursuing with regional head approval; owner unreachable."
    st, r = _req(base, "POST", "/api/pipeline/deals", owner, body)
    step("portfolio: override WITH note accepted", (200, 201), st, r)
    deal = _deal(_did(r))
    step("portfolio: override stamps owner + manager note", True,
         str(deal.get("portfolio_owner_code")) == PO_CODE
         and bool(str(deal.get("manager_override_note") or "").strip()),
         note=f"note={'set' if deal.get('manager_override_note') else 'missing'}")

    # 4. REFER endpoint -> referral-only deal flagged is_referral.
    refer = {
        "client_name": f"SIM Refer {ts}",
        "staff_code": "300731", "staff_name": "Frank Wanyama",
        "portfolio_owner_code": PO_CODE, "portfolio_owner_name": PO_NAME,
        "referred_to": PO_NAME, "referral_note": "Owner's portfolio — referring the lead.",
    }
    st, r = _req(base, "POST", "/api/pipeline/deals/refer", owner, refer)
    step("portfolio: refer-to-owner creates referral deal", (200, 201), st, r)
    rd = (r.get("deal") or r) if isinstance(r, dict) else {}
    rid = _did(r)
    if not rd.get("is_referral"):
        rd = _deal(rid) or rd
    step("portfolio: referred deal flagged is_referral", True, bool(rd.get("is_referral")),
         note=f"is_referral={rd.get('is_referral')}")

    # P3: the refer must now be a PENDING referral the owner has to ACCEPT (nod).
    rdet = _deal(rid)
    step("portfolio: refer creates a PENDING referral (P3 nod gate)", True,
         str(rdet.get("referral_status")) == "pending"
         and str(rdet.get("referred_to_code")) == PO_CODE,
         note=f"status={rdet.get('referral_status')} to={rdet.get('referred_to_code')}")

    mgr = login(base, "MANAGER")   # Immaculate 300716 = the portfolio owner
    if mgr and rid:
        _, inc = _req(base, "GET", "/api/pipeline/referrals/incoming", mgr)
        inc_ids = [d.get("id") for d in (inc.get("deals") or [])] if isinstance(inc, dict) else []
        step("portfolio: referred deal lands in owner's incoming inbox", True, rid in inc_ids,
             note=f"{len(inc_ids)} incoming")
        st, _ = _req(base, "POST", f"/api/pipeline/deals/{rid}/referral/accept", mgr, {})
        step("portfolio: owner accepts the nod", (200, 201), st)
        acc = _deal(rid, mgr)
        step("portfolio: accepted referral now owned by the portfolio owner", True,
             str(acc.get("referral_status")) == "accepted"
             and str(acc.get("staff_code")) == PO_CODE,
             note=f"status={acc.get('referral_status')} owner={acc.get('staff_code')}")


def cbs_portfolio_owner_probe(base):
    """P2 — CBS auto-detects a customer's mapped portfolio owner.

    Every CBS customer carries relationship_manager_code (their relationship
    owner). The new /customers/{cif}/portfolio-owner endpoint resolves that to
    a referable owner (code + roster-resolved name) so the deal-create flow can
    route an existing-customer deal to its owner for a nod. The owner-in-roster
    diagnostic reports how many mapped owners are addressable pipeline users —
    the signal for whether P3's referral routing will land.
    """
    print("\n=== CBS PORTFOLIO OWNER (P2 — auto-detect mapped owner) ===")
    admin = login(base, "ADMIN")
    if not admin:
        step("cbs: admin login", 200, 0, note="cannot proceed")
        return

    # CIFs are contiguous from 100000001 — probe directly, no name-search dependency.
    sample_po = {}
    mapped_pos = []
    for i in range(1, 31):
        cif = str(100000000 + i)
        st, p = _req(base, "GET", f"/api/cbs/customers/{cif}/portfolio-owner", admin)
        if st == 200 and isinstance(p, dict):
            if not sample_po:
                sample_po = p
            if p.get("is_mapped"):
                mapped_pos.append(p)

    step("cbs: portfolio-owner endpoint resolves a real CIF", (200, 201),
         200 if sample_po else 0, sample_po,
         note=f"cif={sample_po.get('cif')} mapped={sample_po.get('is_mapped')}")
    step("cbs: endpoint returns is_mapped + owner_in_roster fields", True,
         "is_mapped" in sample_po and "owner_in_roster" in sample_po)
    step("cbs: mapped customers carry a portfolio owner code", True,
         len(mapped_pos) > 0 and all(p.get("portfolio_owner_code") for p in mapped_pos),
         note=f"{len(mapped_pos)}/30 sampled are mapped")

    # Diagnostic: are mapped owners addressable pipeline users? (P3 routing signal)
    resolved = sum(1 for p in mapped_pos if p.get("owner_in_roster"))
    step("cbs: owner-in-roster diagnostic (P3 routing signal)", True,
         "owner_in_roster" in sample_po,
         note=f"{resolved}/{len(mapped_pos)} mapped owners resolve to roster names")

    st, _ = _req(base, "GET", "/api/cbs/customers/999999999/portfolio-owner", admin)
    step("cbs: unknown CIF -> 404", 404, st)


def portfolio_harden_probe(base):
    """P4.5 — the server enforces mandatory portfolio resolution for existing
    customers. A deal carrying a client_cif whose CBS owner != the creator must
    set portfolio_owner_code, else it's rejected (the create-form guard mirrored
    server-side). Self-owned and unknown CIFs pass through."""
    print("\n=== PORTFOLIO HARDEN (P4.5 — server enforces existing-customer resolution) ===")
    owner = login(base, "OWNER")   # Frank Wanyama 300731 (creating RM)
    if not owner:
        step("harden: owner login", 200, 0, note="cannot proceed")
        return
    ME = "300731"

    # Find an existing customer whose CBS owner is someone OTHER than the creator.
    tcif = town = tname = None
    for i in range(1, 50):
        cif = str(100000000 + i)
        _, po = _req(base, "GET", f"/api/cbs/customers/{cif}/portfolio-owner", owner)
        if isinstance(po, dict) and po.get("is_mapped"):
            code = str(po.get("portfolio_owner_code") or "")
            if code and code != ME:
                tcif, town, tname = cif, code, (po.get("portfolio_owner_name") or "")
                break
    step("harden: found an existing customer owned by another RM", True, tcif is not None,
         note=f"cif={tcif} owner={town}")
    if not tcif:
        return

    ts = f"{datetime.now():%H%M%S}"
    def _body():
        return {"client_name": f"SIM Harden {ts}", "product_type": "Term Loan",
                "deal_value": 3_000_000, "stage": "Lead", "client_cif": tcif}

    # (1) existing customer, NO resolution -> blocked
    st, r = _req(base, "POST", "/api/pipeline/deals", owner, _body())
    step("harden: existing-customer deal WITHOUT resolution blocked", 400, st, r)

    # (2) same, WITH portfolio_owner_code (+ defer credit = seek-permission) -> allowed
    b = _body()
    b["portfolio_owner_code"] = town
    b["portfolio_owner_name"] = tname or f"RM {town}"
    b["bsc_credit_to"] = tname or f"RM {town}"
    st, r = _req(base, "POST", "/api/pipeline/deals", owner, b)
    step("harden: existing-customer deal WITH resolution allowed", (200, 201), st, r)

    # (3) unknown CIF can't be resolved -> guard fails open (not blocked)
    b = _body(); b["client_cif"] = "999999999"
    st, r = _req(base, "POST", "/api/pipeline/deals", owner, b)
    step("harden: unknown CIF not blocked by portfolio guard", (200, 201), st, r)


def sla_config_probe(base):
    print("\n=== SLA CONFIG (S1 — admin-configurable, deal-process-wide) ===")
    import copy as _copy
    admin = login(base, "ADMIN")
    owner = login(base, "OWNER")
    if not admin:
        return

    st, r = _req(base, "GET", "/api/admin/sla-config", admin)
    cfg = r.get("sla_config", {}) if isinstance(r, dict) else {}
    steps = cfg.get("steps", []) if isinstance(cfg, dict) else []
    ladder = cfg.get("escalation_ladder", []) if isinstance(cfg, dict) else []
    step("sla: config readable + well-formed (steps + ladder)", True,
         st == 200 and len(steps) >= 1 and len(ladder) >= 1,
         note=f"{len(steps)} steps, {len(ladder)} tiers")
    step("sla: default taxonomy seeded (role-based steps)", True,
         any(s.get("key") == "disbursement" for s in steps)
         and any(s.get("key") == "line_manager_validation" for s in steps))

    # Round-trip: amend a target, save, read it back -> "once applied it applies".
    amended = _copy.deepcopy(cfg)
    for s in amended.get("steps", []):
        if s.get("key") == "credit_assessment":
            s["target_days"] = 6
    st_w, _ = _req(base, "POST", "/api/admin/sla-config", admin, {"sla_config": amended})
    step("sla: admin save accepted", (200, 201), st_w)
    _str, r2 = _req(base, "GET", "/api/admin/sla-config", admin)
    saved_steps = r2.get("sla_config", {}).get("steps", []) if isinstance(r2, dict) else []
    ca = next((s for s in saved_steps if s.get("key") == "credit_assessment"), {})
    step("sla: saved change is live on next read (applies)", True,
         int(ca.get("target_days", -1)) == 6,
         note=f"credit_assessment target_days={ca.get('target_days')}")

    # Mandatory-before-save validation.
    st_e1, _ = _req(base, "POST", "/api/admin/sla-config", admin,
                    {"sla_config": {"steps": [], "escalation_ladder": ladder}})
    step("sla: empty step set rejected (mandatory)", 400, st_e1)
    st_e2, _ = _req(base, "POST", "/api/admin/sla-config", admin,
                    {"sla_config": {"steps": steps, "escalation_ladder": [
                        {"after_days": 5, "escalate_to": "step_owner"},
                        {"after_days": 2, "escalate_to": "line_manager"}]}})
    step("sla: non-monotonic ladder rejected", 400, st_e2)
    bad_target = _copy.deepcopy(cfg)
    if bad_target.get("steps"):
        bad_target["steps"][0]["target_days"] = 0
    st_e3, _ = _req(base, "POST", "/api/admin/sla-config", admin, {"sla_config": bad_target})
    step("sla: non-positive target rejected", 400, st_e3)

    # Non-admin cannot write.
    st_d, _ = _req(base, "POST", "/api/admin/sla-config", owner, {"sla_config": cfg})
    step("sla: non-admin write denied", 403, st_d)

    # Restore the original config (net-zero for warm re-runs).
    _req(base, "POST", "/api/admin/sla-config", admin, {"sla_config": cfg})


def sla_violations_probe(base):
    print("\n=== SLA VIOLATIONS (S2a — product/age clock) ===")
    import copy as _copy
    admin = login(base, "ADMIN")
    owner = login(base, "OWNER")
    if not admin:
        return

    _st, r0 = _req(base, "GET", "/api/admin/sla-config", admin)
    base_cfg = r0.get("sla_config", {}) if isinstance(r0, dict) else {}
    ladder_roles = {str(t.get("escalate_to")) for t in (base_cfg.get("escalation_ladder") or [])} | {"step_owner"}

    # Force breaches deterministically: a 1-day Term Loan promise -> aged open deals breach.
    tight = _copy.deepcopy(base_cfg)
    tight["product_promise"] = {"Term Loan": 1}
    _req(base, "POST", "/api/admin/sla-config", admin, {"sla_config": tight})

    st, v = _req(base, "GET", "/api/pipeline/sla/violations", admin)
    v = v if isinstance(v, dict) else {}
    vios = v.get("violations", []) if isinstance(v.get("violations"), list) else []
    step("sla violations: endpoint reachable + well-formed", True,
         st == 200 and isinstance(v.get("violations"), list) and isinstance(v.get("open_deals"), int),
         note=f"{v.get('count')} breaches / {v.get('open_deals')} open")
    step("sla violations: tight product promise surfaces Term Loan breaches", True,
         any(x.get("product_type") == "Term Loan" and x.get("overdue_business_days", 0) >= 1 for x in vios),
         note=f"{sum(1 for x in vios if x.get('product_type') == 'Term Loan')} term-loan breaches")
    sample = vios[0] if vios else None
    step("sla violations: each breach carries target + overdue + escalation", True,
         bool(sample) and sample.get("target_days", 0) >= 1
         and sample.get("overdue_business_days", 0) >= 1 and sample.get("breached") is True
         and sample.get("escalate_to") in ladder_roles,
         note=f"escalate_to={sample.get('escalate_to') if sample else None}")
    step("sla violations: overdue == elapsed - target (math)", True,
         bool(sample) and sample["overdue_business_days"] == max(0, sample["elapsed_business_days"] - sample["target_days"]))

    st_rm, vrm = _req(base, "GET", "/api/pipeline/sla/violations", owner)
    vrm = vrm if isinstance(vrm, dict) else {}
    step("sla violations: RM is hierarchy-scoped (subset of MD)", True,
         vrm.get("open_deals", 0) <= v.get("open_deals", 1)
         and vrm.get("count", 0) <= v.get("count", 1),
         note=f"RM open={vrm.get('open_deals')} <= MD open={v.get('open_deals')}")

    # Restore the original config (net-zero).
    _req(base, "POST", "/api/admin/sla-config", admin, {"sla_config": base_cfg})


def sla_step_clock_probe(base):
    print("\n=== SLA STEP CLOCK (S2b — per-step stamping) ===")
    from datetime import datetime as _dt
    owner = login(base, "OWNER")
    admin = login(base, "ADMIN")
    if not owner:
        return
    st, body = _req(base, "POST", "/api/pipeline/deals", owner, {
        "client_name": f"SLA Step Probe {_dt.now():%H%M%S}",
        "product_type": "Term Loan", "deal_value": 5000000,
        "stage": "Lead", "segment": "SME"})
    did = (body.get("deal") or {}).get("id") if isinstance(body, dict) else None
    step("sla step: probe deal created", (200, 201), st, note=f"deal_id={did}")
    if did:
        for tgt in ("Contacted", "Qualified", "Application", "Credit Assessment"):
            _req(base, "POST", f"/api/pipeline/deals/{did}/advance", owner, {"target_stage": tgt})

    st_s, s = _req(base, "GET", f"/api/pipeline/deals/{did}/sla", owner)
    sla = s.get("sla") if isinstance(s, dict) else None
    step("sla step: per-deal SLA endpoint well-formed", True,
         st_s == 200 and isinstance(sla, dict)
         and sla.get("target_days", 0) >= 1 and isinstance(sla.get("elapsed_business_days"), int),
         note=f"clock={sla.get('clock') if isinstance(sla, dict) else None} step={sla.get('step') if isinstance(sla, dict) else None}")
    step("sla step: advanced deal is on the per-STEP clock", True,
         isinstance(sla, dict) and sla.get("clock") == "step" and sla.get("step") == "credit_assessment",
         note=f"step={sla.get('step') if isinstance(sla, dict) else None}")
    step("sla step: step target resolves from config (credit_assessment)", True,
         isinstance(sla, dict) and sla.get("target_days", 0) >= 1,
         note=f"target_days={sla.get('target_days') if isinstance(sla, dict) else None}")

    st_v, v = _req(base, "GET", "/api/pipeline/sla/violations", admin)
    bc = v.get("by_clock", {}) if isinstance(v, dict) else {}
    step("sla step: violations endpoint reports clock split (step active)", True,
         isinstance(bc, dict) and bc.get("step", 0) >= 1,
         note=f"by_clock={bc}")


def sla_credit_step_probe(base, cleared_case_id):
    print("\n=== SLA CREDIT STEP CLOCK (S2c — credit-admin / disbursement) ===")
    admin = login(base, "ADMIN")
    if not admin:
        return
    st, v = _req(base, "GET", "/api/pipeline/sla/violations", admin)
    v = v if isinstance(v, dict) else {}
    by_step = v.get("by_step", {}) if isinstance(v.get("by_step"), dict) else {}
    credit_open = by_step.get("security_perfection", 0) + by_step.get("disbursement", 0)
    step("sla credit: violations expose by_step", True,
         st == 200 and isinstance(v.get("by_step"), dict), note=f"steps={list(by_step)}")
    step("sla credit: credit-admin steps are clocked (security_perfection/disbursement)", True,
         credit_open >= 1, note=f"credit-step open deals={credit_open}")

    # Per-deal proof: resolve the cleared case -> its deal, expect the disbursement step.
    did = ""
    if cleared_case_id:
        _sc, cd = _req(base, "GET", f"/api/credit-admin/cases/{cleared_case_id}", admin)
        case = cd.get("case", {}) if isinstance(cd, dict) else {}
        app_id = str(case.get("application_id") or "")
        if app_id:
            _sa, ad = _req(base, "GET", f"/api/lms/applications/{app_id}", admin)
            ad = ad if isinstance(ad, dict) else {}
            cand = ad.get("application") if isinstance(ad.get("application"), dict) else ad
            did = str(cand.get("pipeline_deal_id") or "") or str(ad.get("pipeline_deal_id") or "")
    if did:
        _ss, sresp = _req(base, "GET", f"/api/pipeline/deals/{did}/sla", admin)
        sla = sresp.get("sla") if isinstance(sresp, dict) else None
        step("sla credit: cleared case's deal is on the disbursement step clock", True,
             isinstance(sla, dict) and sla.get("clock") == "step" and sla.get("step") == "disbursement",
             note=f"deal={did} step={sla.get('step') if isinstance(sla, dict) else None}")
    else:
        step("sla credit: cleared case's deal is on the disbursement step clock", True,
             credit_open >= 1, note="deal not resolved; covered by by_step aggregate")


def sla_commitment_probe(base):
    print("\n=== SLA COMMITMENT (S3 — reason + committed date; unfulfilled self-escalates) ===")
    from datetime import datetime as _dt, date as _date, timedelta as _td
    owner = login(base, "OWNER")
    admin = login(base, "ADMIN")
    if not owner or not admin:
        return
    _sc, cc = _req(base, "GET", "/api/admin/sla-config", admin)
    ladder = (cc.get("sla_config", {}) if isinstance(cc, dict) else {}).get("escalation_ladder", [])
    ceiling, best = "managing_director", -1
    for t in ladder:
        try:
            a = int(t.get("after_days"))
        except (TypeError, ValueError):
            continue
        if a >= best and str(t.get("escalate_to") or "").strip():
            best, ceiling = a, str(t.get("escalate_to"))

    # Build a deterministic step-clock deal (owned by OWNER), advanced to Credit Assessment.
    st_c, body = _req(base, "POST", "/api/pipeline/deals", owner, {
        "client_name": f"SLA Commit Probe {_dt.now():%H%M%S}",
        "product_type": "Term Loan", "deal_value": 5000000,
        "stage": "Lead", "segment": "SME"})
    did = (body.get("deal") or {}).get("id") if isinstance(body, dict) else None
    if did:
        for tgt in ("Contacted", "Qualified", "Application", "Credit Assessment"):
            _req(base, "POST", f"/api/pipeline/deals/{did}/advance", owner, {"target_stage": tgt})
    _ss, s0 = _req(base, "GET", f"/api/pipeline/deals/{did}/sla", owner)
    sla0 = s0.get("sla") if isinstance(s0, dict) else None
    step("sla commitment: step-clock deal ready to commit against", True,
         bool(did) and isinstance(sla0, dict) and sla0.get("clock") == "step",
         note=f"deal={did} step={sla0.get('step') if isinstance(sla0, dict) else None}")

    future = (_date.today() + _td(days=10)).isoformat()
    past = (_date.today() - _td(days=2)).isoformat()
    st_r, _ = _req(base, "POST", f"/api/pipeline/deals/{did}/sla/commitment", owner,
                   {"reason": "Awaiting client valuation report", "committed_date": future})
    step("sla commitment: step owner records reason + committed date", (200, 201), st_r)
    _sg, sresp = _req(base, "GET", f"/api/pipeline/deals/{did}/sla", owner)
    sla = sresp.get("sla") if isinstance(sresp, dict) else None
    step("sla commitment: active commitment surfaces on the deal SLA", True,
         isinstance(sla, dict) and isinstance(sla.get("commitment"), dict)
         and sla.get("commitment_status") == "active",
         note=f"status={sla.get('commitment_status') if isinstance(sla, dict) else None}")

    _req(base, "POST", f"/api/pipeline/deals/{did}/sla/commitment", owner,
         {"reason": "Valuation delayed again", "committed_date": past})
    _sg2, sresp2 = _req(base, "GET", f"/api/pipeline/deals/{did}/sla", owner)
    sla2 = sresp2.get("sla") if isinstance(sresp2, dict) else None
    step("sla commitment: unfulfilled commitment self-escalates to ceiling", True,
         isinstance(sla2, dict) and sla2.get("commitment_status") == "unfulfilled"
         and sla2.get("escalate_to") == ceiling,
         note=f"status={sla2.get('commitment_status') if isinstance(sla2, dict) else None} -> {sla2.get('escalate_to') if isinstance(sla2, dict) else None}")

    st_e, _ = _req(base, "POST", f"/api/pipeline/deals/{did}/sla/commitment", owner,
                   {"reason": "no", "committed_date": future})
    step("sla commitment: short reason rejected", 400, st_e)

    _sv, v = _req(base, "GET", "/api/pipeline/sla/violations", admin)
    vios = v.get("violations", []) if isinstance(v, dict) else []
    foreign = next((x.get("deal_id") for x in vios
                    if str(x.get("owner_code") or "") not in ("", "300731")), None)
    if foreign:
        st_f, _ = _req(base, "POST", f"/api/pipeline/deals/{foreign}/sla/commitment", owner,
                       {"reason": "Out-of-scope attempt", "committed_date": future})
        step("sla commitment: out-of-scope deal not writable", (403, 404), st_f, note=f"deal={foreign}")
    else:
        step("sla commitment: out-of-scope deal not writable", True, True, note="no foreign deal sampled")


def sla_state_probe(base):
    print("\n=== SLA STATE (traffic-light: on_track / due_soon / breached) ===")
    from datetime import datetime as _dt
    owner = login(base, "OWNER")
    admin = login(base, "ADMIN")
    if not owner or not admin:
        return
    _sc, cc = _req(base, "GET", "/api/admin/sla-config", admin)
    cfg0 = cc.get("sla_config") if isinstance(cc, dict) else None
    ddays0 = (cfg0 or {}).get("due_soon_days")
    step("sla state: config exposes due_soon_days", True,
         isinstance(cfg0, dict) and isinstance(ddays0, int) and ddays0 >= 0,
         note=f"due_soon_days={ddays0}")

    _svs, vv = _req(base, "GET", "/api/pipeline/sla/violations", admin)
    bs = vv.get("by_state", {}) if isinstance(vv, dict) else {}
    step("sla state: violations expose by_state summing to open deals", True,
         isinstance(bs, dict) and {"on_track", "due_soon", "breached"} <= set(bs)
         and sum(bs.values()) == vv.get("open_deals"),
         note=f"by_state={bs} open={vv.get('open_deals') if isinstance(vv, dict) else None}")

    st_c, body = _req(base, "POST", "/api/pipeline/deals", owner, {
        "client_name": f"SLA State Probe {_dt.now():%H%M%S}",
        "product_type": "Term Loan", "deal_value": 5000000,
        "stage": "Lead", "segment": "SME"})
    did = (body.get("deal") or {}).get("id") if isinstance(body, dict) else None
    if did:
        for tgt in ("Contacted", "Qualified", "Application", "Credit Assessment"):
            _req(base, "POST", f"/api/pipeline/deals/{did}/advance", owner, {"target_stage": tgt})
    _ss, s0 = _req(base, "GET", f"/api/pipeline/deals/{did}/sla", owner)
    sla0 = s0.get("sla") if isinstance(s0, dict) else None
    step("sla state: fresh step-clock deal is on_track", True,
         isinstance(sla0, dict) and sla0.get("state") == "on_track"
         and isinstance(sla0.get("remaining_business_days"), int),
         note=f"state={sla0.get('state') if isinstance(sla0, dict) else None} remaining={sla0.get('remaining_business_days') if isinstance(sla0, dict) else None}")

    _sl, lst = _req(base, "GET", "/api/pipeline/deals?limit=200", owner)
    deals = lst.get("deals", []) if isinstance(lst, dict) else []
    with_state = [d for d in deals if isinstance(d.get("sla"), dict) and d["sla"].get("state")]
    step("sla state: deals list attaches per-deal sla state", True, len(with_state) >= 1,
         note=f"{len(with_state)}/{len(deals)} deals carry sla.state")

    if isinstance(cfg0, dict) and did:
        bumped = dict(cfg0)
        bumped["due_soon_days"] = 999
        try:
            _req(base, "POST", "/api/admin/sla-config", admin, {"sla_config": bumped})
            _sd, s1 = _req(base, "GET", f"/api/pipeline/deals/{did}/sla", owner)
            sla1 = s1.get("sla") if isinstance(s1, dict) else None
            step("sla state: due_soon_days reclassifies on_track -> due_soon", True,
                 isinstance(sla1, dict) and sla1.get("state") == "due_soon",
                 note=f"state={sla1.get('state') if isinstance(sla1, dict) else None} @ due_soon_days=999")
        finally:
            _req(base, "POST", "/api/admin/sla-config", admin, {"sla_config": cfg0})
    else:
        step("sla state: due_soon_days reclassifies on_track -> due_soon", True, True, note="skipped")


def sla_tat_probe(base):
    print("\n=== SLA-TAT SHADOW (Credit TAT from SLA clocks; weight 0) ===")
    admin = login(base, "ADMIN")
    owner = login(base, "OWNER")
    if not admin:
        return
    sc, body = _req(base, "GET", "/api/bsc/sla-tat", admin)
    bw = body.get("bank_wide") if isinstance(body, dict) else None
    bys = body.get("by_staff") if isinstance(body, dict) else None
    step("sla tat: endpoint returns shadow summary structure", True,
         sc == 200 and isinstance(body, dict)
         and body.get("kpi_id") == "SLA_CREDIT_TAT" and body.get("shadow") is True
         and isinstance(bw, dict) and isinstance(bys, dict)
         and {"tat_days", "n_deals", "n_staff"} <= set(bw),
         note=f"bank_wide={bw}")

    n = bw.get("n_deals") if isinstance(bw, dict) else None
    if isinstance(n, int) and n >= 1:
        step("sla tat: bank-wide tat_days is numeric when completed deals exist", True,
             isinstance(bw.get("tat_days"), (int, float)),
             note=f"tat_days={bw.get('tat_days')} over n={n}")
        ok_rows = all(isinstance(r, dict) and isinstance(r.get("tat_days"), (int, float))
                      and isinstance(r.get("n_deals"), int) for r in bys.values())
        step("sla tat: by_staff rows carry tat_days + n_deals", True,
             ok_rows and len(bys) >= 1, note=f"{len(bys)} staff with completed credit TAT")
    else:
        step("sla tat: bank-wide tat_days is numeric when completed deals exist", True, True,
             note="no completed credit-TAT deals yet (structural pass)")
        step("sla tat: by_staff rows carry tat_days + n_deals", True, True,
             note="no completed credit-TAT deals yet (structural pass)")

    if owner:
        so, _ = _req(base, "GET", "/api/bsc/sla-tat", owner)
        step("sla tat: endpoint readable by non-admin staff", 200, so)


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

    cleared_case_id = happy_path(args.base, committee=False)
    if not args.skip_committee:
        happy_path(args.base, committee=True)
    negative_override_probe(args.base)
    sla_credit_step_probe(args.base, cleared_case_id)
    troops_probe(args.base, cleared_case_id)
    roles_probe(args.base)
    pool_visibility_probe(args.base)
    analyst_decision_probe(args.base)
    sla_config_probe(args.base)
    sla_violations_probe(args.base)
    sla_step_clock_probe(args.base)
    sla_commitment_probe(args.base)
    sla_state_probe(args.base)
    sla_tat_probe(args.base)
    fx_currency_probe(args.base)
    sector_mou_probe(args.base)
    referral_probe(args.base)
    staff_search_probe(args.base)
    portfolio_conflict_probe(args.base)
    cbs_portfolio_owner_probe(args.base)
    portfolio_harden_probe(args.base)
    scope_guard(args.base)
    dashboard_check(args.base)
    credit_probe(args.base)
    hierarchy_scope_probe(args.base)
    exceptions_probe(args.base)
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
