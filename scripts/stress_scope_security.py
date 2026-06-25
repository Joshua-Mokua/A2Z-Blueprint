#!/usr/bin/env python3
"""scripts/stress_scope_security.py — STRESS PHASE 2: scope / security.

Verifies that a low-privilege user (an RM with single-person scope) CANNOT
read or mutate deals owned by someone OUTSIDE their cascade. Every pipeline
mutation endpoint is attacked with a REAL foreign deal id + the low-priv token;
each must return 403/404, never 200.

This is the compliance-critical check: a cross-cascade leak means one RM can
see or act on another's portfolio. The functional harness only spot-checks one
fake id; this hits every mutation with a real foreign deal.

Reports OK (blocked) / HOLE (leak — investigate) / INFO (couldn't test).
Run against a live API on :8502.

    python scripts/stress_scope_security.py
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
    "OWNER":   {"username": "frank0731",      "password": "EcoStaff0731"},  # RM 300731
    "MANAGER": {"username": "immaculate0716", "password": "EcoStaff0716"},
    "ADMIN":   {"username": "william001",     "password": "EcoStaff0001"},  # MD, sees all
}
OWNER_CODE = "300731"

FINDINGS = []


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
            payload = {"detail": raw[:200]}
        return e.code, payload
    except Exception as e:
        return 0, {"detail": f"{type(e).__name__}: {e}"}


_TOKENS = {}


def login(base, key):
    if key in _TOKENS:
        return _TOKENS[key]
    p = PERSONAS[key]
    st, body = _req(base, "POST", "/api/auth/login", body=p)
    if st == 429:
        print(f"  [rate-limited on {key}; waiting 61s]")
        time.sleep(61)
        st, body = _req(base, "POST", "/api/auth/login", body=p)
    tok = body.get("access_token") or body.get("token")
    if st == 200 and tok:
        _TOKENS[key] = tok
        return tok
    print(f"  [LOGIN FAIL] {key} -> {st} {body.get('detail','')}")
    return None


def record(kind, label, detail=""):
    FINDINGS.append({"kind": kind, "label": label, "detail": detail})
    tag = {"OK": "OK  ", "HOLE": "HOLE", "INFO": "INFO"}[kind]
    extra = f"  :: {detail}" if detail else ""
    print(f"  [{tag}] {label}{extra}")


def _find_foreign_deal(base, admin):
    """As MD/admin, find a REAL deal NOT owned by OWNER_CODE (foreign to Frank).
    Prefer one that is open + early-stage so mutation attempts are meaningful."""
    st, body = _req(base, "GET", "/api/pipeline/deals?limit=500", admin)
    deals = body.get("deals") if isinstance(body, dict) else None
    if not isinstance(deals, list):
        # some list endpoints return a bare list
        deals = body if isinstance(body, list) else []
    foreign = None
    foreign_open = None
    for d in deals:
        if not isinstance(d, dict):
            continue
        sc = str(d.get("staff_code") or d.get("owner_code") or "")
        if sc and sc != OWNER_CODE:
            did = d.get("id") or d.get("deal_id")
            if not did:
                continue
            if foreign is None:
                foreign = (did, sc, d.get("stage"))
            stage = str(d.get("stage") or "")
            if stage not in ("Closed Won", "Closed Lost") and foreign_open is None:
                foreign_open = (did, sc, stage)
                break
    return foreign_open or foreign


def probe_scope(base, owner, admin):
    print("\n=== PHASE 2: scope / security — foreign-deal mutation attempts ===")
    fd = _find_foreign_deal(base, admin)
    if not fd:
        record("INFO", "no foreign deal found to test", "admin list returned nothing usable")
        return
    did, owner_code, stage = fd
    print(f"  foreign deal = {did} (owned by {owner_code}, stage {stage}); "
          f"attacking as OWNER 300731")

    # (label, method, path, body)  — every mutation must block the foreign caller.
    attacks = [
        ("GET detail",            "GET",  f"/api/pipeline/deals/{did}", None),
        ("advance",               "POST", f"/api/pipeline/deals/{did}/advance", {"new_stage": "Qualified", "note": "scope stress"}),
        ("PUT update",            "PUT",  f"/api/pipeline/deals/{did}", {"client_name": "HACKED"}),
        ("submit-to-credit",      "POST", f"/api/pipeline/deals/{did}/submit-to-credit", {}),
        ("validate",              "POST", f"/api/pipeline/deals/{did}/validate", {"approved": True}),
        ("refer",                 "POST", f"/api/pipeline/deals/{did}/refer", {"to_staff_code": "300716", "note": "scope stress"}),
        ("referral accept",       "POST", f"/api/pipeline/deals/{did}/referral/accept", {}),
        ("referral decline",      "POST", f"/api/pipeline/deals/{did}/referral/decline", {"reason": "scope stress test"}),
        ("referral reassign",     "POST", f"/api/pipeline/deals/{did}/referral/reassign", {"to_staff_code": "300716"}),
        ("cancel request",        "POST", f"/api/pipeline/deals/{did}/cancel/request", {"reason": "scope stress test"}),
        ("cancel approve",        "POST", f"/api/pipeline/deals/{did}/cancel/approve", {}),
        ("sla commitment",        "POST", f"/api/pipeline/deals/{did}/sla/commitment", {"reason": "scope stress test", "committed_date": "2026-12-31"}),
    ]
    for label, method, path, body in attacks:
        st, rbody = _req(base, method, path, owner, body)
        detail = str(rbody.get("detail", ""))[:70] if isinstance(rbody, dict) else ""
        if st in (403, 404):
            record("OK", f"{label}: foreign deal blocked", f"st={st}")
        elif st in (200, 201):
            record("HOLE", f"{label}: foreign deal MUTATED/READ by non-owner",
                   f"st={st} — CROSS-CASCADE LEAK on {did}")
        elif st == 400:
            # 400 = reached handler but rejected on payload/state, NOT on scope.
            # That means the scope gate did NOT block first — suspicious.
            record("INFO", f"{label}: 400 (handler reached before auth — should be 403/404 after Phase-2 hardening)",
                   f"detail={detail}")
        else:
            record("INFO", f"{label}: unexpected status", f"st={st} detail={detail}")


def probe_low_priv_admin(base, owner):
    print("\n=== PHASE 2b: low-priv user hitting ADMIN endpoints ===")
    admin_attacks = [
        ("role registry",        "GET",  "/api/admin/roles", None),
        ("product-flows upsert",  "POST", "/api/admin/product-flows", {"product": "HACK", "stages": [{"stage": "Lead", "target_days": 1}]}),
        ("pipeline-config write", "POST", "/api/admin/pipeline-config", {"product_catalogue": {"X": ["Y"]}}),
        ("committee tiers write", "POST", "/api/lms/committee/tiers", {"tiers": [{"tier": 1, "name": "HACK"}]}),
        ("pool visibility write", "POST", "/api/lms/config/pool-visibility", {"roles": ["hacker"]}),
        ("sla config write",      "POST", "/api/admin/sla-config", {"steps": []}),
    ]
    for label, method, path, body in admin_attacks:
        st, rbody = _req(base, method, path, owner, body)
        detail = str(rbody.get("detail", ""))[:60] if isinstance(rbody, dict) else ""
        if st == 403:
            record("OK", f"admin {label}: non-admin denied", f"st=403")
        elif st in (200, 201):
            record("HOLE", f"admin {label}: NON-ADMIN ALLOWED",
                   f"st={st} — privilege escalation")
        elif st in (404, 405):
            record("INFO", f"admin {label}: {st} (route shape)", f"detail={detail}")
        else:
            record("INFO", f"admin {label}: status {st}", f"detail={detail}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8502")
    args = ap.parse_args()
    base = args.base

    print(f"A2Z STRESS — scope/security @ {base}  ({datetime.now():%Y-%m-%d %H:%M:%S})")
    admin = login(base, "ADMIN")
    owner = login(base, "OWNER")
    if not (admin and owner):
        print("FATAL: need ADMIN + OWNER logins"); sys.exit(2)

    probe_scope(base, owner, admin)
    probe_low_priv_admin(base, owner)

    holes = [f for f in FINDINGS if f["kind"] == "HOLE"]
    infos = [f for f in FINDINGS if f["kind"] == "INFO"]
    oks = [f for f in FINDINGS if f["kind"] == "OK"]
    print("\n" + "=" * 60)
    print(f"SCOPE/SECURITY STRESS: {len(oks)} guards held, "
          f"{len(holes)} HOLES, {len(infos)} to review")
    if holes:
        print("\nHOLES (leak / escalation — investigate):")
        for f in holes:
            print(f"  - {f['label']}  ::  {f['detail']}")
    if infos:
        print("\nREVIEW:")
        for f in infos:
            print(f"  - {f['label']}  ::  {f['detail']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
