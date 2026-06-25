#!/usr/bin/env python3
"""scripts/stress_state_machine.py — STRESS PHASE 1: state-machine integrity.

Attacks the pipeline/credit state machine along the paths the happy-path
harness never walks: backward transitions, same-stage re-advance, reopening
closed deals, double-handoff idempotency, and mutating terminal deals.

These are the bugs that cause SILENT corruption (a deal disbursed twice, a
closed deal reopened, two LMS apps from one handoff) — they pass functional
testing because functional testing only walks the legal path.

This script REPORTS findings; it does not assert a target count. Each probe
prints OK (guard held) / HOLE (guard missing — investigate) / INFO (observed
behaviour, judgement call). Run against a live API on :8502.

    python scripts/stress_state_machine.py
    python scripts/stress_state_machine.py --base http://127.0.0.1:8502
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
    "MANAGER": {"username": "immaculate0716", "password": "EcoStaff0716"},
    "ADMIN":   {"username": "william001",     "password": "EcoStaff0001"},
}

FINDINGS = []  # {kind: OK|HOLE|INFO, label, detail}


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
    except Exception as e:
        return 0, {"detail": f"{type(e).__name__}: {e}"}


_TOKEN_CACHE: dict = {}


def login(base, persona_key):
    if persona_key in _TOKEN_CACHE:
        return _TOKEN_CACHE[persona_key]
    p = PERSONAS[persona_key]
    st, body = _req(base, "POST", "/api/auth/login", body=p)
    if st == 429:
        print(f"  [rate-limited on {persona_key} login — waiting 61s]")
        time.sleep(61)
        st, body = _req(base, "POST", "/api/auth/login", body=p)
    tok = body.get("access_token") or body.get("token")
    if st == 200 and tok:
        _TOKEN_CACHE[persona_key] = tok
        return tok
    print(f"  [LOGIN FAIL] {persona_key} ({p['username']}) -> {st} {body.get('detail','')}")
    return None


def record(kind, label, detail=""):
    FINDINGS.append({"kind": kind, "label": label, "detail": detail})
    tag = {"OK": "OK  ", "HOLE": "HOLE", "INFO": "INFO"}[kind]
    extra = f"  :: {detail}" if detail else ""
    print(f"  [{tag}] {label}{extra}")


def _deal_id(body):
    return (body.get("deal") or {}).get("id") if isinstance(body, dict) else None


def _stage_of(base, owner, deal_id):
    st, body = _req(base, "GET", f"/api/pipeline/deals/{deal_id}", owner)
    if st == 200 and isinstance(body, dict):
        return (body.get("deal") or {}).get("stage")
    return None


def _create_deal(base, owner, stage="Lead", product="Term Loan"):
    body = {
        "client_name": f"SM Stress {datetime.now():%H%M%S%f}",
        "product_type": product, "deal_value": 1_000_000,
        "stage": stage, "segment": "SME",
    }
    st, b = _req(base, "POST", "/api/pipeline/deals", owner, body)
    return st, _deal_id(b), b


def _advance(base, tok, deal_id, new_stage, note="stress"):
    return _req(base, "POST", f"/api/pipeline/deals/{deal_id}/advance",
                tok, {"new_stage": new_stage, "note": note})


# ── PROBE 1: backward transition ─────────────────────────────────────
def probe_backward(base, owner):
    print("\n=== PROBE 1: backward transition (Qualified -> Lead) ===")
    st, did, _ = _create_deal(base, owner)
    if not did:
        record("INFO", "could not create deal for backward probe", f"st={st}")
        return
    _advance(base, owner, did, "Contacted")
    _advance(base, owner, did, "Qualified")
    before = _stage_of(base, owner, did)
    st, body = _advance(base, owner, did, "Lead")
    after = _stage_of(base, owner, did)
    if st in (200, 201) and after == "Lead":
        record("INFO", "backward transition ACCEPTED (Qualified->Lead)",
               f"deal moved {before}->{after}; is this intended? a deal can regress")
    elif st == 400:
        record("OK", "backward transition rejected", f"detail={str(body.get('detail',''))[:80]}")
    else:
        record("INFO", "backward transition unexpected result",
               f"st={st} before={before} after={after}")


# ── PROBE 2: same-stage re-advance ───────────────────────────────────
def probe_same_stage(base, owner):
    print("\n=== PROBE 2: same-stage re-advance (Qualified -> Qualified) ===")
    st, did, _ = _create_deal(base, owner)
    if not did:
        record("INFO", "could not create deal for same-stage probe", f"st={st}")
        return
    _advance(base, owner, did, "Contacted")
    _advance(base, owner, did, "Qualified")
    st, body = _advance(base, owner, did, "Qualified")
    after = _stage_of(base, owner, did)
    if st in (200, 201):
        record("INFO", "same-stage re-advance ACCEPTED",
               f"stage still {after}; may re-stamp SLA / re-fire BSC each call")
    elif st == 400:
        record("OK", "same-stage re-advance rejected", f"detail={str(body.get('detail',''))[:80]}")
    else:
        record("INFO", "same-stage unexpected", f"st={st} after={after}")


# ── PROBE 3: reopen a closed deal ────────────────────────────────────
def probe_reopen_closed(base, owner):
    print("\n=== PROBE 3: reopen a closed deal (Closed Won/Lost -> Negotiation) ===")
    for terminal in ("Closed Won", "Closed Lost"):
        st, did, _ = _create_deal(base, owner)
        if not did:
            record("INFO", f"could not create deal for reopen probe ({terminal})", f"st={st}")
            continue
        _advance(base, owner, did, "Contacted")
        _advance(base, owner, did, "Qualified")
        stc, _ = _advance(base, owner, did, terminal)
        if stc not in (200, 201):
            record("INFO", f"could not reach {terminal}", f"st={stc}")
            continue
        # now try to reopen
        st, body = _advance(base, owner, did, "Negotiation")
        after = _stage_of(base, owner, did)
        if st in (200, 201) and after == "Negotiation":
            record("HOLE", f"{terminal} deal REOPENED to Negotiation",
                   f"a terminal deal should not move; now at {after}")
        elif st == 400:
            record("OK", f"{terminal} deal cannot be reopened", f"detail={str(body.get('detail',''))[:70]}")
        else:
            record("INFO", f"{terminal} reopen unexpected", f"st={st} after={after}")


# ── PROBE 4: double handoff idempotency ──────────────────────────────
def probe_double_handoff(base, owner, manager):
    print("\n=== PROBE 4: double advance-to-Compliance (LMS handoff idempotency) ===")
    st, did, _ = _create_deal(base, owner)
    if not did:
        record("INFO", "could not create deal for handoff probe", f"st={st}")
        return
    for s in ("Contacted", "Qualified", "Proposal", "Negotiation"):
        _advance(base, owner, did, s)
    st1, b1 = _advance(base, owner, did, "Compliance")
    app1 = b1.get("lms_application_id") if isinstance(b1, dict) else None
    # immediately advance to Compliance again (same stage) — should NOT mint a 2nd app
    st2, b2 = _advance(base, owner, did, "Compliance")
    app2 = b2.get("lms_application_id") if isinstance(b2, dict) else None
    if app1 and app2 and app1 != app2:
        record("HOLE", "double handoff minted TWO LMS apps",
               f"app1={app1} app2={app2} — duplicate credit application")
    elif app1 and (not app2 or app1 == app2):
        record("OK", "handoff idempotent (no duplicate LMS app)",
               f"app={app1}; 2nd call app2={app2}")
    else:
        record("INFO", "handoff probe inconclusive",
               f"st1={st1} app1={app1} st2={st2} app2={app2}")


# ── PROBE 5: mutate a terminal deal (submit / refer) ─────────────────
def probe_mutate_terminal(base, owner):
    print("\n=== PROBE 5: submit-to-credit / refer on a Closed Lost deal ===")
    st, did, _ = _create_deal(base, owner)
    if not did:
        record("INFO", "could not create deal for terminal-mutate probe", f"st={st}")
        return
    _advance(base, owner, did, "Contacted")
    _advance(base, owner, did, "Qualified")
    _advance(base, owner, did, "Closed Lost")
    # submit-to-credit on a closed-lost deal
    st, body = _req(base, "POST", f"/api/pipeline/deals/{did}/submit-to-credit", owner, {})
    if st in (200, 201):
        record("HOLE", "submit-to-credit ACCEPTED on Closed Lost deal",
               "a lost deal should not be submittable to credit")
    else:
        record("OK", "submit-to-credit blocked on Closed Lost",
               f"st={st} detail={str(body.get('detail',''))[:70]}")
    # refer a closed-lost deal
    st, body = _req(base, "POST", f"/api/pipeline/deals/{did}/refer", owner,
                    {"to_staff_code": "300716", "note": "stress"})
    if st in (200, 201):
        record("INFO", "refer ACCEPTED on Closed Lost deal",
               "review: should a terminal deal be referrable?")
    else:
        record("OK", "refer blocked/handled on Closed Lost", f"st={st}")


# ── PROBE 6: create directly at a terminal/LMS stage ─────────────────
def probe_create_at_bad_stage(base, owner):
    print("\n=== PROBE 6: create deal directly at terminal / LMS stage ===")
    for bad in ("Closed Won", "Compliance", "Disbursed"):
        st, did, body = _create_deal(base, owner, stage=bad)
        if did:
            record("HOLE", f"create at '{bad}' ACCEPTED",
                   f"deal born at {bad} bypasses the workflow; id={did}")
        else:
            record("OK", f"create at '{bad}' rejected",
                   f"st={st} detail={str(body.get('detail',''))[:60]}")



# ── PROBE 7: PUT-endpoint stage bypass ───────────────────────────────
def probe_put_bypass(base, owner):
    print("\n=== PROBE 7: stage change via PUT (must be blocked -> use /advance) ===")
    st, did, _ = _create_deal(base, owner)
    if not did:
        record("INFO", "could not create deal for PUT-bypass probe", f"st={st}")
        return
    _advance(base, owner, did, "Contacted")
    _advance(base, owner, did, "Qualified")
    # try to jump to Closed Won via PUT (bypassing advance guards)
    st, body = _req(base, "PUT", f"/api/pipeline/deals/{did}", owner, {"stage": "Closed Won"})
    after = _stage_of(base, owner, did)
    if st in (200, 201) and after == "Closed Won":
        record("HOLE", "PUT moved deal to Closed Won (bypassed advance guards)",
               f"now at {after}; stage transitions must go through /advance")
    elif st == 400:
        record("OK", "PUT rejects stage change (forces /advance)",
               f"detail={str(body.get('detail',''))[:70]}")
    else:
        record("INFO", "PUT-bypass unexpected", f"st={st} after={after}")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8502")
    args = ap.parse_args()
    base = args.base

    print(f"A2Z STRESS — state-machine integrity @ {base}  ({datetime.now():%Y-%m-%d %H:%M:%S})")
    admin = login(base, "ADMIN")
    owner = login(base, "OWNER") or admin
    manager = login(base, "MANAGER") or admin
    if not owner:
        print("FATAL: could not log in owner/admin"); sys.exit(2)

    probe_backward(base, owner)
    probe_same_stage(base, owner)
    probe_reopen_closed(base, owner)
    probe_double_handoff(base, owner, manager)
    probe_mutate_terminal(base, owner)
    probe_create_at_bad_stage(base, owner)
    probe_put_bypass(base, owner)

    holes = [f for f in FINDINGS if f["kind"] == "HOLE"]
    infos = [f for f in FINDINGS if f["kind"] == "INFO"]
    oks = [f for f in FINDINGS if f["kind"] == "OK"]
    print("\n" + "=" * 60)
    print(f"STATE-MACHINE STRESS: {len(oks)} guards held, "
          f"{len(holes)} HOLES, {len(infos)} to review")
    if holes:
        print("\nHOLES (guard missing — investigate):")
        for f in holes:
            print(f"  - {f['label']}  ::  {f['detail']}")
    if infos:
        print("\nREVIEW (observed behaviour — judgement call):")
        for f in infos:
            print(f"  - {f['label']}  ::  {f['detail']}")
    print("=" * 60)


if __name__ == "__main__":
    main()
