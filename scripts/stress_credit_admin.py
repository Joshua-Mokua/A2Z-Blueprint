#!/usr/bin/env python3
"""scripts/stress_credit_admin.py — CA-2 step 1: the FAILING probe (red first).

Credit-admin cases persist through CreditAdminManager._save -> whole-file
write_text on credit_admin.json with NO locking. Concurrent mutations race:
each request loads the whole list, mutates its case, rewrites the entire file —
last writer wins, the rest are lost. This probe reproduces and MEASURES that on
the credit-admin path specifically (stress_concurrency.py only covers pipeline).

It writes a UNIQUE security-perfection reference per call and re-reads to count
how many actually survived. Expected on the current JSON path: HOLES (lost
writes). After CA-2 (sync wired + reads DB-first), the same probe should go
GREEN — that red->green flip is the proof CA-2 fixed concurrency, not the
sequential 295/295 harness (which cannot see this class of bug).

  Probe S (control): 2 cases written SEQUENTIALLY must both persist. If this
                     fails, the payload/route is wrong — abort (no false red).
  Probe A: N DISTINCT cases, one unique perfection each, fired in parallel.
           Count distinct cases whose write survived. (lost-update analog.)
  Probe B: ONE case, N unique perfections fired in parallel.
           Count how many of the N appends survived. (two-officers-one-case.)

Read-only setup; appends test perfections to existing cases (harmless on dev
data, re-runnable — each run uses a fresh run id). Run against a live API:8502.

    python scripts\\stress_credit_admin.py
    python scripts\\stress_credit_admin.py --n 15
"""
from __future__ import annotations
import argparse, json, sys, time
import urllib.error, urllib.request
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed

PERSONAS = {"ADMIN": {"username": "william001", "password": "EcoStaff0001"}}
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
        except Exception: payload = {"detail": raw[:200]}
        return e.code, payload
    except Exception as e:
        return 0, {"detail": f"{type(e).__name__}: {e}"}


_TOK = {}
def login(base, key="ADMIN"):
    if key in _TOK: return _TOK[key]
    st, body = _req(base, "POST", "/api/auth/login", body=PERSONAS[key])
    if st == 429:
        time.sleep(61); st, body = _req(base, "POST", "/api/auth/login", body=PERSONAS[key])
    tok = body.get("access_token") or body.get("token")
    if st == 200 and tok:
        _TOK[key] = tok; return tok
    print(f"  [LOGIN FAIL] {key} -> {st} {body.get('detail','')}"); return None


def record(kind, label, detail=""):
    FINDINGS.append({"kind": kind, "label": label, "detail": detail})
    tag = {"OK": "OK  ", "HOLE": "HOLE", "INFO": "INFO"}[kind]
    print(f"  [{tag}] {label}" + (f"  :: {detail}" if detail else ""))


def _case_ids(base, token, want):
    st, body = _req(base, "GET", "/api/credit-admin/cases", token)
    cases = body.get("cases", []) if isinstance(body, dict) else []
    ids = [c.get("id") for c in cases if c.get("id")]
    return ids[:want]


def _add_perfection(base, token, case_id, ref):
    return _req(base, "POST", f"/api/credit-admin/cases/{case_id}/perfection",
                token, {"security_type": "Debenture", "registration_reference": ref})


def _ref_present(base, token, case_id, ref):
    """True if `ref` appears anywhere in the case (robust to key naming)."""
    st, body = _req(base, "GET", f"/api/credit-admin/cases/{case_id}", token)
    return ref in json.dumps(body)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8502")
    ap.add_argument("--n", type=int, default=10)
    a = ap.parse_args()
    base, N = a.base, a.n
    run = datetime.now().strftime("%H%M%S%f")

    print(f"A2Z STRESS — credit-admin concurrency @ {base} (n={N})  ({datetime.now():%Y-%m-%d %H:%M:%S})")
    token = login(base)
    if not token:
        print("  cannot proceed without ADMIN token"); sys.exit(2)

    ids = _case_ids(base, token, N + 2)
    if len(ids) < 3:
        print(f"  !! need >=3 credit-admin cases, found {len(ids)}"); sys.exit(2)

    # ── Probe S: sequential control (guards against false red) ────────────
    print("=== PROBE S: sequential control (writes MUST persist) ===")
    s_cases = ids[:2]
    s_ok = 0
    for i, cid in enumerate(s_cases):
        ref = f"CAPROBE-{run}-S-{i}"
        st, _ = _add_perfection(base, token, cid, ref)
        if st in (200, 201) and _ref_present(base, token, cid, ref):
            s_ok += 1
    if s_ok == len(s_cases):
        record("OK", "sequential control: writes persist", f"{s_ok}/{len(s_cases)}")
    else:
        record("HOLE", "sequential control FAILED — payload/route wrong, not a race",
               f"{s_ok}/{len(s_cases)} persisted")
        print("  aborting: cannot trust concurrency result if sequential fails.")
        _summary(); sys.exit(1)

    # ── Probe A: N distinct cases, parallel, one unique write each ─────────
    print("=== PROBE A: N parallel writes to DISTINCT cases (lost update) ===")
    a_cases = ids[2:2 + N]
    refs = {cid: f"CAPROBE-{run}-A-{i}" for i, cid in enumerate(a_cases)}

    def _wa(cid):
        st, _ = _add_perfection(base, token, cid, refs[cid]); return cid, st
    with ThreadPoolExecutor(max_workers=N) as ex:
        list(as_completed([ex.submit(_wa, cid) for cid in a_cases]))
    persisted = sum(1 for cid in a_cases if _ref_present(base, token, cid, refs[cid]))
    if persisted == len(a_cases):
        record("OK", "distinct-case writes: all persisted (serialized)",
               f"{persisted}/{len(a_cases)}")
    else:
        record("HOLE", "distinct-case writes: LOST updates",
               f"{persisted}/{len(a_cases)} persisted — {len(a_cases)-persisted} clobbered")

    # ── Probe B: ONE case, N parallel appends ─────────────────────────────
    print("=== PROBE B: N parallel appends to ONE case (two-officers-one-case) ===")
    b_case = ids[-1]
    b_refs = [f"CAPROBE-{run}-B-{i}" for i in range(N)]

    def _wb(ref):
        st, _ = _add_perfection(base, token, b_case, ref); return ref, st
    with ThreadPoolExecutor(max_workers=N) as ex:
        list(as_completed([ex.submit(_wb, r) for r in b_refs]))
    st, body = _req(base, "GET", f"/api/credit-admin/cases/{b_case}", token)
    blob = json.dumps(body)
    survived = sum(1 for r in b_refs if r in blob)
    if survived == N:
        record("OK", "single-case appends: all survived (serialized)", f"{survived}/{N}")
    else:
        record("HOLE", "single-case appends: LOST appends",
               f"{survived}/{N} survived — {N-survived} clobbered")

    _summary()


def _summary():
    ok = sum(1 for f in FINDINGS if f["kind"] == "OK")
    holes = [f for f in FINDINGS if f["kind"] == "HOLE"]
    print("=" * 60)
    print(f"CREDIT-ADMIN CONCURRENCY: {ok} OK, {len(holes)} HOLES")
    if holes:
        print("HOLES (data loss / race):")
        for f in holes:
            print(f"  - {f['label']}  ::  {f['detail']}")
    print("=" * 60)
    if holes:
        print("Expected RED on the current JSON path. CA-2 (sync wired + reads")
        print("DB-first) should flip these to OK. That red->green IS the proof.")


if __name__ == "__main__":
    main()
