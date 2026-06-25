#!/usr/bin/env python3
"""scripts/stress_input_robustness.py — STRESS PHASE 3: input robustness.

Attacks the create/advance/refer input surface with malformed, extreme, and
adversarial payloads the happy path never sends:

  - privileged-field injection (manager_validated, referral_status, override
    flags, is_referral) — does extra="allow" let a caller create a deal that's
    born pre-validated, bypassing the manager-validation gate?
  - numeric edges on deal_value: NaN, Infinity, negative, absurdly large,
    string-encoded, list/dict type confusion
  - string content on client_name: oversized (1MB), null bytes, control chars,
    XSS/script payloads (stored-XSS risk if rendered), SQL-ish strings
  - type confusion on stage / product_type

Reports OK (handled safely) / HOLE (accepted something dangerous) / INFO.
A 500 on a malformed payload is a HOLE (unhandled crash = DoS surface).
Run against a live API on :8502.

    python scripts/stress_input_robustness.py
"""
from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.request
from datetime import datetime

PERSONAS = {
    "OWNER":   {"username": "frank0731",      "password": "EcoStaff0731"},
    "ADMIN":   {"username": "william001",     "password": "EcoStaff0001"},
}

FINDINGS = []


def _req(base, method, path, token=None, body=None, timeout=30, raw_body=None):
    url = base.rstrip("/") + path
    if raw_body is not None:
        data = raw_body.encode() if isinstance(raw_body, str) else raw_body
    else:
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
            payload = {"detail": raw[:200]}
        return e.code, payload
    except Exception as e:
        return 0, {"detail": f"{type(e).__name__}: {e}"}


_TOK = {}


def login(base, key):
    if key in _TOK:
        return _TOK[key]
    st, body = _req(base, "POST", "/api/auth/login", body=PERSONAS[key])
    if st == 429:
        time.sleep(61)
        st, body = _req(base, "POST", "/api/auth/login", body=PERSONAS[key])
    tok = body.get("access_token") or body.get("token")
    if st == 200 and tok:
        _TOK[key] = tok
        return tok
    print(f"  [LOGIN FAIL] {key} -> {st}")
    return None


def record(kind, label, detail=""):
    FINDINGS.append({"kind": kind, "label": label, "detail": detail})
    tag = {"OK": "OK  ", "HOLE": "HOLE", "INFO": "INFO"}[kind]
    print(f"  [{tag}] {label}" + (f"  :: {detail}" if detail else ""))


def _deal_id(body):
    return (body.get("deal") or {}).get("id") if isinstance(body, dict) else None


def _base_deal(**over):
    d = {"client_name": f"IR {datetime.now():%H%M%S%f}", "product_type": "Term Loan",
         "deal_value": 1_000_000, "stage": "Lead", "segment": "SME"}
    d.update(over)
    return d


# ── PROBE 1: privileged-field injection at create ────────────────────
def probe_priv_injection(base, owner):
    print("\n=== PROBE 1: privileged-field injection at create (extra=allow) ===")
    cases = [
        ("manager_validated=true", {"manager_validated": True}),
        ("referral_status=accepted", {"referral_status": "accepted"}),
        ("is_referral=true", {"is_referral": True}),
        ("disbursed_under_override=true", {"disbursed_under_override": True}),
        ("staff_code=foreign(300261)", {"staff_code": "300261"}),
        ("portfolio_owner_code=foreign", {"portfolio_owner_code": "300261"}),
    ]
    for label, inject in cases:
        body = _base_deal(**inject)
        st, rb = _req(base, "POST", "/api/pipeline/deals", owner, body)
        did = _deal_id(rb)
        if not did:
            record("OK", f"{label}: create rejected", f"st={st}")
            continue
        # fetch back and see if the injected field stuck
        st2, detail = _req(base, "GET", f"/api/pipeline/deals/{did}", owner)
        deal = (detail.get("deal") or {}) if isinstance(detail, dict) else {}
        field = list(inject.keys())[0]
        got = deal.get(field)
        want = inject[field]
        if field in ("staff_code", "portfolio_owner_code"):
            # these MUST be server-stamped to the caller (300731), not the injected value
            if str(got) == str(want):
                record("HOLE", f"{label}: injected value STUCK", f"{field}={got} (should be caller 300731)")
            else:
                record("OK", f"{label}: server-stamped, injection ignored", f"{field}={got}")
        else:
            if got == want:
                record("HOLE", f"{label}: injected value STUCK", f"deal born with {field}={got}")
            else:
                record("OK", f"{label}: injection ignored/reset", f"{field}={got}")


# ── PROBE 2: deal_value numeric edges ────────────────────────────────
def probe_value_edges(base, owner):
    print("\n=== PROBE 2: deal_value numeric edges ===")
    # raw JSON so we can send NaN/Infinity (not valid JSON but some parsers accept)
    raw_cases = [
        ("NaN", '{"client_name":"IRnan","product_type":"Term Loan","deal_value":NaN,"stage":"Lead","segment":"SME"}'),
        ("Infinity", '{"client_name":"IRinf","product_type":"Term Loan","deal_value":Infinity,"stage":"Lead","segment":"SME"}'),
    ]
    for label, raw in raw_cases:
        st, rb = _req(base, "POST", "/api/pipeline/deals", owner, raw_body=raw)
        if st in (200, 201):
            record("HOLE", f"deal_value={label}: ACCEPTED", "non-finite value stored")
        elif st == 500:
            record("HOLE", f"deal_value={label}: 500 crash", str(rb.get("detail",""))[:60])
        else:
            record("OK", f"deal_value={label}: rejected", f"st={st}")
    typed_cases = [
        ("negative", -5_000_000),
        ("huge_1e308", 1e308),
        ("string_number", "1000000"),
        ("string_junk", "not-a-number"),
        ("list", [1, 2, 3]),
        ("dict", {"$ne": None}),
        ("bool", True),
    ]
    for label, val in typed_cases:
        body = _base_deal(deal_value=val)
        st, rb = _req(base, "POST", "/api/pipeline/deals", owner, body)
        did = _deal_id(rb)
        if st == 500:
            record("HOLE", f"deal_value={label}: 500 crash", str(rb.get("detail",""))[:60])
        elif label in ("negative",) and did:
            record("HOLE", f"deal_value={label}: ACCEPTED", "negative value stored")
        elif label in ("string_number",) and did:
            record("INFO", f"deal_value={label}: accepted (coerced)", "string coerced to number — acceptable")
        elif did:
            record("INFO", f"deal_value={label}: accepted", f"review: stored a {label}")
        else:
            record("OK", f"deal_value={label}: rejected", f"st={st}")


# ── PROBE 3: client_name string content ──────────────────────────────
def probe_string_content(base, owner):
    print("\n=== PROBE 3: client_name string content ===")
    cases = [
        ("1MB_string", "A" * 1_000_000),
        ("null_bytes", "Acme\x00Corp"),
        ("control_chars", "Acme\x01\x02\x07Corp"),  # now rejected by validator
        ("xss_script", "<script>alert(1)</script>"),
        ("xss_img", "<img src=x onerror=alert(1)>"),
        ("sql_ish", "'; DROP TABLE deals;--"),
        ("rtl_override", "Acme\u202eEvil"),
        ("emoji_unicode", "Acme 🏦💰 Søme Çorp"),
    ]
    for label, name in cases:
        body = _base_deal(client_name=name)
        st, rb = _req(base, "POST", "/api/pipeline/deals", owner, body)
        did = _deal_id(rb)
        if st == 500:
            record("HOLE", f"client_name={label}: 500 crash", str(rb.get("detail",""))[:50])
        elif label == "1MB_string" and did:
            record("INFO", f"client_name={label}: accepted", "no length cap — review (DoS/storage)")
        elif label in ("xss_script", "xss_img") and did:
            # stored as-is is OK *if* frontend escapes on render; flag for review
            st2, detail = _req(base, "GET", f"/api/pipeline/deals/{did}", owner)
            stored = ((detail.get("deal") or {}).get("client_name") if isinstance(detail, dict) else "")
            record("INFO", f"client_name={label}: stored verbatim", "OK iff frontend escapes on render (verify)")
        elif label == "null_bytes" and did:
            record("INFO", f"client_name={label}: accepted", "null byte stored — review")
        elif did:
            record("OK", f"client_name={label}: accepted + handled", "no crash")
        else:
            record("OK", f"client_name={label}: rejected", f"st={st}")


# ── PROBE 4: type confusion on stage / product ───────────────────────
def probe_type_confusion(base, owner):
    print("\n=== PROBE 4: type confusion on stage / product_type ===")
    cases = [
        ("stage=int", {"stage": 123}),
        ("stage=list", {"stage": ["Lead"]}),
        ("stage=null", {"stage": None}),
        ("product=int", {"product_type": 999}),
        ("product=dict", {"product_type": {"x": 1}}),
        ("missing_all", {}),
    ]
    for label, over in cases:
        if label == "missing_all":
            body = {}
        else:
            body = _base_deal(**over)
        st, rb = _req(base, "POST", "/api/pipeline/deals", owner, body)
        if st == 500:
            record("HOLE", f"{label}: 500 crash", str(rb.get("detail",""))[:60])
        elif st in (400, 422):
            record("OK", f"{label}: rejected cleanly", f"st={st}")
        elif _deal_id(rb):
            record("INFO", f"{label}: accepted", "review: coerced a bad type")
        else:
            record("OK", f"{label}: no deal created", f"st={st}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8502")
    args = ap.parse_args()
    base = args.base
    print(f"A2Z STRESS — input robustness @ {base}  ({datetime.now():%Y-%m-%d %H:%M:%S})")
    owner = login(base, "OWNER")
    if not owner:
        print("FATAL: need OWNER login"); sys.exit(2)

    probe_priv_injection(base, owner)
    probe_value_edges(base, owner)
    probe_string_content(base, owner)
    probe_type_confusion(base, owner)

    holes = [f for f in FINDINGS if f["kind"] == "HOLE"]
    infos = [f for f in FINDINGS if f["kind"] == "INFO"]
    oks = [f for f in FINDINGS if f["kind"] == "OK"]
    print("\n" + "=" * 60)
    print(f"INPUT ROBUSTNESS: {len(oks)} handled, {len(holes)} HOLES, {len(infos)} to review")
    if holes:
        print("\nHOLES (accepted something dangerous / crashed):")
        for f in holes:
            print(f"  - {f['label']}  ::  {f['detail']}")
    if infos:
        print("\nREVIEW:")
        for f in infos:
            print(f"  - {f['label']}  ::  {f['detail']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
