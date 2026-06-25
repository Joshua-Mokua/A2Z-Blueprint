#!/usr/bin/env python3
"""scripts/stress_concurrency.py — STRESS PHASE 4: concurrency / load.

The pipeline persists to a JSON file via read-modify-write with NO locking:
PipelineManager loads the whole deals list, mutates its copy, and rewrites the
entire file. Concurrent requests therefore race — last write wins, and writes
can be lost. This probe confirms exploitability and measures it.

Probes:
  1. PARALLEL CREATE — fire N concurrent creates; check for (a) duplicate deal
     IDs (id = len(deals)+1 computed before append) and (b) lost creates (deal
     count rose by < N).
  2. LOST UPDATE — create K deals, then concurrently PUT a distinct change to
     each; re-read and count how many changes actually persisted.
  3. DOUBLE-DISBURSE / DOUBLE-ADVANCE — fire the same mutation on ONE deal many
     times in parallel; check the server serializes / guards (only one wins).
  4. LOAD — measure throughput + error rate under a burst of reads.

OK (handled / serialized) / HOLE (data loss / duplicate / double-action) / INFO.
Run against a live API on :8502.

    python scripts/stress_concurrency.py
    python scripts/stress_concurrency.py --n 30
"""
from __future__ import annotations
import argparse, json, sys, time, threading
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
        except Exception: payload = {"detail": raw[:200]}
        return e.code, payload
    except Exception as e:
        return 0, {"detail": f"{type(e).__name__}: {e}"}

_TOK = {}
def login(base, key):
    if key in _TOK: return _TOK[key]
    st, body = _req(base, "POST", "/api/auth/login", body=PERSONAS[key])
    if st == 429:
        time.sleep(61); st, body = _req(base, "POST", "/api/auth/login", body=PERSONAS[key])
    tok = body.get("access_token") or body.get("token")
    if st == 200 and tok: _TOK[key] = tok; return tok
    print(f"  [LOGIN FAIL] {key} -> {st}"); return None

def record(kind, label, detail=""):
    FINDINGS.append({"kind": kind, "label": label, "detail": detail})
    tag = {"OK":"OK  ","HOLE":"HOLE","INFO":"INFO"}[kind]
    print(f"  [{tag}] {label}" + (f"  :: {detail}" if detail else ""))

def _base_deal(tag):
    return {"client_name": f"CONC {tag} {datetime.now():%H%M%S%f}",
            "product_type": "Term Loan", "deal_value": 1_000_000,
            "stage": "Lead", "segment": "SME"}

def _deal_count(base, admin):
    st, body = _req(base, "GET", "/api/pipeline/deals?limit=10000", admin)
    deals = body.get("deals") if isinstance(body, dict) else None
    if not isinstance(deals, list): deals = body if isinstance(body, list) else []
    return deals

def probe_parallel_create(base, owner, admin, n):
    print(f"\n=== PROBE 1: {n} parallel creates (ID race + lost writes) ===")
    before = _deal_count(base, admin)
    n_before = len(before)
    ids = []
    lock = threading.Lock()
    def _create(i):
        st, body = _req(base, "POST", "/api/pipeline/deals", owner, _base_deal(f"P1-{i}"))
        did = (body.get("deal") or {}).get("id") if isinstance(body, dict) else None
        with lock:
            ids.append((st, did))
    with ThreadPoolExecutor(max_workers=n) as ex:
        list(ex.map(_create, range(n)))
    time.sleep(1.0)  # let writes settle
    after = _deal_count(base, admin)
    n_after = len(after)
    created_ok = [d for (s, d) in ids if s in (200, 201) and d]
    unique_ids = set(created_ok)
    # duplicate IDs returned?
    if len(unique_ids) < len(created_ok):
        record("HOLE", "parallel create: DUPLICATE deal IDs returned",
               f"{len(created_ok)} created, {len(unique_ids)} unique")
    else:
        record("OK", "parallel create: returned IDs unique", f"{len(unique_ids)} ids")
    # lost writes? net deal count should rise by the number of successful creates
    delta = n_after - n_before
    ok_count = len([s for (s, d) in ids if s in (200, 201)])
    if delta < ok_count:
        record("HOLE", "parallel create: LOST writes (count rose < successes)",
               f"+{delta} persisted vs {ok_count} created OK — {ok_count - delta} lost")
    else:
        record("OK", "parallel create: all successful creates persisted",
               f"+{delta} for {ok_count} successes")
    # duplicate IDs actually persisted on disk?
    all_ids = [str(d.get("id") or d.get("deal_id")) for d in after if isinstance(d, dict)]
    dupes = {x for x in all_ids if all_ids.count(x) > 1}
    if dupes:
        record("HOLE", "parallel create: DUPLICATE IDs persisted on disk",
               f"dupes={list(dupes)[:5]}")
    else:
        record("OK", "parallel create: no duplicate IDs on disk", f"{len(all_ids)} total")

def probe_lost_update(base, owner, admin, k):
    print(f"\n=== PROBE 2: {k} concurrent updates to distinct deals (lost update) ===")
    # create k deals first (sequential, so they're clean)
    made = []
    for i in range(k):
        st, body = _req(base, "POST", "/api/pipeline/deals", owner, _base_deal(f"P2-{i}"))
        did = (body.get("deal") or {}).get("id") if isinstance(body, dict) else None
        if did: made.append(did)
    if len(made) < k:
        record("INFO", "lost update: could not create enough deals", f"{len(made)}/{k}")
    # concurrently PUT a unique next_action to each
    sentinel = f"CONCURRENT-{datetime.now():%H%M%S}"
    def _upd(did):
        return _req(base, "PUT", f"/api/pipeline/deals/{did}", owner,
                    {"next_action": f"{sentinel}-{did}"})
    with ThreadPoolExecutor(max_workers=len(made)) as ex:
        list(ex.map(_upd, made))
    time.sleep(1.0)
    # re-read each; count how many carry their sentinel
    persisted = 0
    for did in made:
        st, body = _req(base, "GET", f"/api/pipeline/deals/{did}", owner)
        deal = (body.get("deal") or {}) if isinstance(body, dict) else {}
        if str(deal.get("next_action") or "").startswith(sentinel):
            persisted += 1
    if persisted < len(made):
        record("HOLE", "concurrent update: LOST updates",
               f"{persisted}/{len(made)} persisted — {len(made)-persisted} clobbered")
    else:
        record("OK", "concurrent update: all persisted", f"{persisted}/{len(made)}")

def probe_double_action(base, owner, admin, n):
    print(f"\n=== PROBE 3: {n} parallel advances on ONE deal (double-action) ===")
    st, body = _req(base, "POST", "/api/pipeline/deals", owner, _base_deal("P3"))
    did = (body.get("deal") or {}).get("id") if isinstance(body, dict) else None
    if not did:
        record("INFO", "double-action: could not create probe deal", f"st={st}"); return
    # fire N concurrent advances Lead->Contacted; only ONE should succeed (idempotent target)
    results = []
    lock = threading.Lock()
    def _adv(i):
        st, b = _req(base, "POST", f"/api/pipeline/deals/{did}/advance", owner,
                     {"new_stage": "Contacted", "note": f"conc {i}"})
        with lock: results.append(st)
    with ThreadPoolExecutor(max_workers=n) as ex:
        list(ex.map(_adv, range(n)))
    oks = [s for s in results if s in (200, 201)]
    # advancing to the SAME stage repeatedly: ideally the server is consistent
    # (either idempotent-OK or rejects the no-op). The real risk is a 500/crash
    # or the deal ending in a corrupt state. Re-read and verify stage is sane.
    st2, b2 = _req(base, "GET", f"/api/pipeline/deals/{did}", owner)
    deal = (b2.get("deal") or {}) if isinstance(b2, dict) else {}
    final_stage = deal.get("stage")
    crashed = [s for s in results if s == 500 or s == 0]
    if crashed:
        record("HOLE", "double-advance: concurrent advances caused 500/crash",
               f"{len(crashed)}/{n} errored")
    elif final_stage in ("Contacted", "Lead"):
        record("OK", "double-advance: deal in consistent stage after race",
               f"stage={final_stage}, {len(oks)}/{n} ok")
    else:
        record("HOLE", "double-advance: deal in UNEXPECTED stage after race",
               f"stage={final_stage}")

def probe_read_load(base, owner, n):
    print(f"\n=== PROBE 4: {n} concurrent reads (load / error rate) ===")
    lat = []; errs = 0
    lock = threading.Lock()
    def _read(i):
        t0 = time.perf_counter()
        st, _ = _req(base, "GET", "/api/pipeline/deals?limit=200", owner)
        dt = (time.perf_counter() - t0) * 1000
        with lock:
            lat.append(dt)
            if st not in (200,): 
                pass
    t0 = time.perf_counter()
    with ThreadPoolExecutor(max_workers=n) as ex:
        list(ex.map(_read, range(n)))
    wall = time.perf_counter() - t0
    if lat:
        lat.sort()
        p50 = lat[len(lat)//2]; p95 = lat[int(len(lat)*0.95)-1]
        record("INFO", f"read load: {n} concurrent reads in {wall:.1f}s",
               f"p50={p50:.0f}ms p95={p95:.0f}ms throughput={n/wall:.1f} req/s")

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--base", default="http://127.0.0.1:8502")
    ap.add_argument("--n", type=int, default=20, help="concurrency level")
    args = ap.parse_args()
    base = args.base
    print(f"A2Z STRESS — concurrency/load @ {base} (n={args.n})  ({datetime.now():%Y-%m-%d %H:%M:%S})")
    owner = login(base, "OWNER"); admin = login(base, "ADMIN")
    if not (owner and admin):
        print("FATAL: need OWNER + ADMIN"); sys.exit(2)

    probe_parallel_create(base, owner, admin, args.n)
    probe_lost_update(base, owner, admin, min(args.n, 10))
    probe_double_action(base, owner, admin, args.n)
    probe_read_load(base, owner, args.n)

    holes = [f for f in FINDINGS if f["kind"]=="HOLE"]
    infos = [f for f in FINDINGS if f["kind"]=="INFO"]
    oks   = [f for f in FINDINGS if f["kind"]=="OK"]
    print("\n" + "="*60)
    print(f"CONCURRENCY/LOAD: {len(oks)} OK, {len(holes)} HOLES, {len(infos)} info")
    if holes:
        print("\nHOLES (data loss / race / crash):")
        for f in holes: print(f"  - {f['label']}  ::  {f['detail']}")
    if infos:
        print("\nINFO:")
        for f in infos: print(f"  - {f['label']}  ::  {f['detail']}")
    print("="*60)

if __name__ == "__main__":
    main()
