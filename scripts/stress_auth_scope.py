#!/usr/bin/env python3
"""scripts/stress_auth_scope.py — reproduce the auth-store / enrichment race.

Background (from efb8fbd): under concurrent load a legitimately-scoped user
intermittently receives 403 "outside cascade scope" on their OWN resources.
Diagnosis pointed at _enrich_identity_from_store (auth_jwt.py:240) constructing
a fresh UserManager() per request — but the mechanism was never pinned (the
file _save is atomic, so it is NOT a torn read). This probe REPRODUCES the
symptom so the cause can be instrumented and a fix gated red->green.

A scoped RM acting on their OWN deal must never get 403/404. Any spurious 403
here is the enrichment race: staff_code failed to fill -> empty scope -> denied.

  Probe R — N concurrent scoped READS of the user's own deal.
  Probe U — N concurrent scoped UPDATES of the user's own deal.
  Probe L — N threads each: FRESH login + scoped read (max construction/write
            pressure on the per-request UserManager path).

    python scripts\\stress_auth_scope.py
    python scripts\\stress_auth_scope.py --n 30 --rounds 3
"""
from __future__ import annotations
import argparse, json, sys, time
import urllib.error, urllib.request
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

PERSONAS = {
    "OWNER": {"username": "frank0731",  "password": "EcoStaff0731"},
    "ADMIN": {"username": "william001", "password": "EcoStaff0001"},
}
FINDINGS = []


def _req(base, method, path, token=None, body=None, timeout=60):
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
        try: payload = json.loads(raw)
        except Exception: payload = {"detail": raw[:160]}
        return e.code, payload
    except Exception as e:
        return 0, {"detail": f"{type(e).__name__}: {e}"}


def login(base, key):
    st, body = _req(base, "POST", "/api/auth/login", body=PERSONAS[key])
    if st == 429:
        time.sleep(61); st, body = _req(base, "POST", "/api/auth/login", body=PERSONAS[key])
    tok = body.get("access_token") or body.get("token")
    if st == 200 and tok:
        return tok
    print(f"  [LOGIN FAIL] {key} -> {st} {body.get('detail','')}")
    return None


def record(kind, label, detail=""):
    FINDINGS.append({"kind": kind, "label": label, "detail": detail})
    tag = {"OK": "OK  ", "HOLE": "HOLE", "INFO": "INFO"}[kind]
    print(f"  [{tag}] {label}" + (f"  :: {detail}" if detail else ""))


def _base_deal(tag):
    return {"client_name": f"AuthScope {tag}", "product_type": "Term Loan",
            "deal_value": 1_000_000, "stage": "Lead"}


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8502")
    ap.add_argument("--n", type=int, default=20)
    ap.add_argument("--rounds", type=int, default=2)
    a = ap.parse_args()
    base, N, ROUNDS = a.base, a.n, a.rounds

    print(f"A2Z STRESS — auth-store / enrichment scope race @ {base} (n={N}, rounds={ROUNDS})"
          f"  ({datetime.now():%Y-%m-%d %H:%M:%S})")
    owner = login(base, "OWNER")
    if not owner:
        print("  cannot proceed without OWNER token"); sys.exit(2)

    st, body = _req(base, "POST", "/api/pipeline/deals", owner, _base_deal("seed"))
    did = (body.get("deal") or {}).get("id") if isinstance(body, dict) else None
    if st not in (200, 201) or not did:
        print(f"  could not create owner deal (st={st}) — cannot probe scope"); sys.exit(2)
    print(f"  owner deal: {did}")

    def _count(codes):
        spurious = [c for c in codes if c in (403, 404)]
        return len(spurious), {c: codes.count(c) for c in sorted(set(codes))}

    # ── Probe R: concurrent scoped reads of own deal ──
    print("=== PROBE R: N concurrent scoped READS of own deal ===")
    bad_total = 0
    for _ in range(ROUNDS):
        with ThreadPoolExecutor(max_workers=N) as ex:
            codes = [f.result() for f in as_completed(
                [ex.submit(lambda: _req(base, "GET", f"/api/pipeline/deals/{did}", owner)[0])
                 for _ in range(N)])]
        bad, dist = _count(codes); bad_total += bad
    if bad_total == 0:
        record("OK", "scoped reads: own deal always authorized", f"0/{N*ROUNDS} spurious 403/404")
    else:
        record("HOLE", "scoped reads: spurious 403/404 on OWN deal (enrichment race)",
               f"{bad_total}/{N*ROUNDS} denied; last dist={dist}")

    # ── Probe U: concurrent scoped updates of own deal ──
    print("=== PROBE U: N concurrent scoped UPDATES of own deal ===")
    bad_total = 0; last = {}
    for _ in range(ROUNDS):
        with ThreadPoolExecutor(max_workers=N) as ex:
            codes = [f.result() for f in as_completed(
                [ex.submit(lambda i=i: _req(base, "PUT", f"/api/pipeline/deals/{did}", owner,
                                            {"next_action": f"auth-scope-{i}"})[0])
                 for i in range(N)])]
        bad, last = _count(codes); bad_total += bad
    if bad_total == 0:
        record("OK", "scoped updates: own deal always authorized", f"0/{N*ROUNDS} spurious 403/404")
    else:
        record("HOLE", "scoped updates: spurious 403/404 on OWN deal (enrichment race)",
               f"{bad_total}/{N*ROUNDS} denied; last dist={last}")

    # ── Probe L: fresh-login + scoped read storm (max write/construction pressure) ──
    print("=== PROBE L: N threads each FRESH login + scoped read ===")
    def _login_then_read(_i):
        tok = login(base, "OWNER")
        if not tok:
            return 0  # login failure recorded separately
        return _req(base, "GET", f"/api/pipeline/deals/{did}", tok)[0]
    bad_total = 0; last = {}
    for _ in range(ROUNDS):
        with ThreadPoolExecutor(max_workers=N) as ex:
            codes = [f.result() for f in as_completed(
                [ex.submit(_login_then_read, i) for i in range(N)])]
        bad, last = _count(codes); bad_total += bad
    if bad_total == 0:
        record("OK", "login+read storm: own deal always authorized", f"0/{N*ROUNDS} spurious 403/404")
    else:
        record("HOLE", "login+read storm: spurious 403/404 on OWN deal (enrichment race)",
               f"{bad_total}/{N*ROUNDS} denied; last dist={last}")

    ok = sum(1 for f in FINDINGS if f["kind"] == "OK")
    holes = [f for f in FINDINGS if f["kind"] == "HOLE"]
    print("=" * 60)
    print(f"AUTH-STORE / SCOPE RACE: {ok} OK, {len(holes)} HOLES")
    for f in holes:
        print(f"  - {f['label']}  ::  {f['detail']}")
    print("=" * 60)
    if holes:
        print("RED reproduced. Next: instrument the per-request UserManager()/_enrich")
        print("path to pin the cause, then gate the fix red->green here.")


if __name__ == "__main__":
    main()
