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
    st_fd, fd = _req(base, "GET", "/api/pipeline/funnel/drill?cls=all&stage=", admin)
    fd_ok = (st_fd == 200 and isinstance(fd, dict)
             and all(k in fd for k in ("totals", "by_product", "by_segment", "by_sector", "deals")))
    step("funnel drill: reachable + well-formed", True, fd_ok,
         note=f"count={fd.get('totals',{}).get('count') if isinstance(fd, dict) else '—'}")
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
    negative_override_probe(args.base)
    fx_currency_probe(args.base)
    sector_mou_probe(args.base)
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
