"""Localize the ~2.1s/deal create latency the stress test surfaced.

Times each component of the create path IN-PROCESS, plus a full API round trip,
so we fix the real bottleneck instead of guessing. Run in the project venv:

  python scripts\\profile_create_latency.py

Prints a per-phase breakdown. Whichever phase dominates is the thing to fix.
"""
from __future__ import annotations
import json, os, sys, time, statistics, urllib.request, urllib.error

# Make `utils` importable no matter where this is launched from.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

REPS = 5


def t(fn, reps=REPS):
    xs = []
    for _ in range(reps):
        s = time.perf_counter()
        try:
            fn()
        except Exception as e:
            return None, f"{type(e).__name__}: {e}"
        xs.append((time.perf_counter() - s) * 1000)
    return statistics.median(xs), None


def line(name, ms, err=""):
    if err:
        print(f"  {name:38} ERROR: {err[:80]}")
    else:
        print(f"  {name:38} {ms:8.1f} ms (median of {REPS})")


def main():
    print("=== Environment ===")
    print(f"  A2Z_USE_DB        = {os.getenv('A2Z_USE_DB', '(unset -> file mode)')}")
    print(f"  A2Z_DB_HOST       = {os.getenv('A2Z_DB_HOST', '(unset)')}")

    print("\n=== In-process component timings ===")

    # 1. Manager construction (file loads)
    try:
        from utils.core import PipelineManager
        ms, err = t(lambda: PipelineManager())
        line("PipelineManager() construction", ms, err)
    except Exception as e:
        line("PipelineManager() construction", None, str(e))

    # 2. Scope resolution — prime suspect (tree walk per request)
    try:
        from utils.api_pipeline_scope import get_visible_staff_codes
        user = {"username": "william001", "staff_code": "300001",
                "role": "Chief Executive & Managing Director", "is_admin": True}
        ms, err = t(lambda: get_visible_staff_codes(user))
        line("get_visible_staff_codes(user)", ms, err)
    except Exception as e:
        line("get_visible_staff_codes(user)", None, str(e))

    # 3. User re-fetch (whoami / UserManager per request)
    try:
        from utils.core import UserManager
        ms, err = t(lambda: UserManager())
        line("UserManager() construction", ms, err)
    except Exception as e:
        line("UserManager() construction", None, str(e))

    # 4. DB round-trip timings — the singleton is `db` (an instance), not module fns.
    try:
        from utils.db import db as _DB
        ms, err = t(lambda: _DB.is_postgres_ready())
        line("db.is_postgres_ready()", ms, err)
        ms, err = t(lambda: _DB.fetch_all("SELECT 1"))
        line("db.fetch_all('SELECT 1')  [1 round trip]", ms, err)
        ms, err = t(lambda: _DB.fetch_all("SELECT id FROM pipeline_deals LIMIT 1"))
        line("db.fetch_all(pipeline_deals)  [1 round trip]", ms, err)
        # First getconn vs warm getconn — is the pool re-connecting each time?
        from utils.db import _get_pool
        pool = _get_pool()
        if pool is not None:
            def _cycle():
                c = pool.getconn(); pool.putconn(c)
            ms, err = t(_cycle)
            line("pool.getconn()+putconn() cycle", ms, err)
    except Exception as e:
        line("DB round-trip timings", None, str(e))

    # 5. Full API create round trip (the real number)
    print("\n=== End-to-end API create (full request) ===")
    base = os.getenv("A2Z_BASE", "http://127.0.0.1:8502")

    def _login():
        req = urllib.request.Request(base + "/api/auth/login",
            data=json.dumps({"username": "william001", "password": "EcoStaff0001"}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        with urllib.request.urlopen(req, timeout=30) as r:
            return json.loads(r.read())["access_token"]
    try:
        tok = _login()
    except Exception as e:
        print(f"  login failed ({e}); is the API running? skipping API timing.")
        return

    def _get(path, auth=True):
        hdr = {"Content-Type": "application/json"}
        if auth:
            hdr["Authorization"] = f"Bearer {tok}"
        req = urllib.request.Request(base + path, headers=hdr, method="GET")
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()

    # Discriminator GETs: health (no middleware auth), me (get_current_user only),
    # deals (read path). Whichever is slow localizes the 2.3s.
    ms, err = t(lambda: _get("/api/health", auth=False)); line("GET /api/health (no auth)", ms, err)
    ms, err = t(lambda: _get("/api/auth/me")); line("GET /api/auth/me (auth only)", ms, err)
    ms, err = t(lambda: _get("/api/pipeline/deals")); line("GET /api/pipeline/deals (read)", ms, err)

    # DECISIVE: is the ~2s the IPv6-first localhost resolution on Windows?
    # Compare the SAME health call over localhost vs 127.0.0.1 (forced IPv4).
    print("\n=== localhost vs 127.0.0.1 (IPv6-fallback test) ===")
    def _health(host):
        req = urllib.request.Request(host + "/api/health", method="GET")
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
    ms, err = t(lambda: _health("http://localhost:8502")); line("GET /api/health via localhost", ms, err)
    ms, err = t(lambda: _health("http://127.0.0.1:8502")); line("GET /api/health via 127.0.0.1", ms, err)
    print("\nIf 127.0.0.1 is ~ms and localhost is ~2s, the 2s is IPv6-first")
    print("localhost resolution in the Python client — NOT a server problem.")

    def _create():
        req = urllib.request.Request(base + "/api/pipeline/deals",
            data=json.dumps({"client_name": "PROFILE", "client_type": "Business",
                             "product_type": "Term Loan", "deal_value": 1000000,
                             "stage": "Lead"}).encode(),
            headers={"Content-Type": "application/json", "Authorization": f"Bearer {tok}"},
            method="POST")
        with urllib.request.urlopen(req, timeout=30) as r:
            r.read()
    ms, err = t(_create, reps=5)
    line("POST /api/pipeline/deals (full)", ms, err)

    print("\nInterpretation: if the full API call >> the sum of the in-process")
    print("phases, the cost is middleware (rate limiter / audit / per-request user")
    print("re-fetch). If get_visible_staff_codes or UserManager dominate, cache them.")


if __name__ == "__main__":
    main()
