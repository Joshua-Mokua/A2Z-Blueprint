# A2Z MIS 360 — Load Testing Runbook

Standard #5 of the master addendum requires the platform to meet four
performance targets. This runbook explains how to verify them with k6.

## The four targets (Standard #5)

| Metric | Target | Test |
|---|---|---|
| API response p95 | < 200 ms | `tests/load/api_p95.js` |
| Dashboard load | < 3 s | covered by `api_p95.js` (kind:dashboard threshold) |
| Concurrent users | 1,000+ | `tests/load/concurrent_users.js` |
| Export 10K rows | < 10 s | `tests/load/export_10k.js` |

A fifth test, `tests/load/baseline_smoke.js`, is the pre-flight sanity
check that runs first.

## Prerequisites

1. **k6 binary** (Grafana's load-testing tool). Install per
   https://grafana.com/docs/k6/latest/set-up/install-k6/ — there are
   one-line installers for macOS (`brew install k6`), Linux
   (`apt`/`dnf` repos), and Windows (`winget`).

2. **The A2Z API running locally** or a deployed test target.
   Start locally with:
   ```bash
   python -m utils.api
   ```
   Default address: `http://localhost:8502`.

3. **A test user with login credentials.** The default fixtures use
   `william001` / `ECOStaff001` (the demo MD account from the v5.x
   bootstrap). If your test environment uses different credentials,
   set `A2Z_TEST_USER` and `A2Z_TEST_PASS`.

## Running the suite

### One-liner (all four tests)

```bash
python scripts/run_load_tests.py
```

This:
1. Checks k6 is installed and the API is reachable
2. Runs each script in sequence with `--summary-export`
3. Aggregates results into `load_results.json` at the project root
4. Exits 0 if all thresholds pass, 1 if any failed, 2 if the API is unreachable

### Subset (e.g. only API p95)

```bash
A2Z_LOAD_TESTS=api_p95 python scripts/run_load_tests.py
```

Comma-separated names: `baseline_smoke,api_p95,export_10k,concurrent_users`.

### Skip the 1k VU test

The `concurrent_users` test is heavy — 1,000 virtual users for 6
minutes. Don't run it on a laptop or shared dev machine. To skip:

```bash
A2Z_SKIP_HEAVY=1 python scripts/run_load_tests.py
```

### Against a remote target

```bash
A2Z_API_BASE=https://staging.example.com \
A2Z_TEST_USER=loadtest \
A2Z_TEST_PASS='...' \
python scripts/run_load_tests.py
```

## Interpreting results

After `run_load_tests.py` completes, look at:

- **Console output** — per-test pass/fail with p95 in ms
- **`load_results.json`** — aggregated, audit-friendly summary
- **`results/<test>.json`** — k6's full per-test summary

The `load_results.json` is what audit gate G18 reads. If it's present,
G18 enforces the thresholds; if not, G18 reports informational.

## Test-by-test detail

### `baseline_smoke.js`
1 VU, 10 s, hits `/api/health` (the only unauthed endpoint).
Asserts p95 < 100 ms. Fails fast if the API is broken before the real
load tests start.

### `api_p95.js`
50 VUs, 60 s, picks a random read endpoint each iteration:
`/api/auth/me`, `/api/health`, `/api/bsc/summary`, `/api/pipeline/summary`,
`/api/credit/summary`, `/api/aml/summary`, `/api/dashboard/md`,
`/api/v1/pipeline_deals?limit=50`. Asserts p95 < 200 ms overall and
p95 < 3 s for dashboard endpoints.

### `concurrent_users.js`
Ramping load: 0 → 1,000 VUs over 2 min, sustained for 3 min, ramped
back to 0 over 1 min. Total runtime ~6 min. Asserts p95 < 500 ms
under peak (note: 5x the steady-load threshold — connection
contention at 1k VUs is expected) and error rate < 2%. The strict
500 ms upper bound means the system stays *responsive*, not snappy.
Hitting `< 200 ms` at 1k VUs would be a heroic result.

### `export_10k.js`
10 VUs, 2 min, calls `POST /api/v1/pipeline_deals/export` with
`limit: 10000`. Asserts each request completes in under 10 s.
**Setup note:** the pilot table needs ≥ 10k rows for the test to be
meaningful. In a fresh staging env you may need to seed data first
(seed script TBD).

## Common failures and fixes

### "k6 binary not found on PATH"
Install k6. See prerequisites above.

### "API not reachable"
Start the API: `python -m utils.api`. Check the port: default 8502,
override with `A2Z_API_PORT` env var. Verify with `curl
http://localhost:8502/api/health`.

### "login failed (HTTP 401)"
Verify `A2Z_TEST_USER` and `A2Z_TEST_PASS` are correct. The default
`william001` / `ECOStaff001` only works in dev/test environments
where the bootstrap user is seeded.

### `api_p95` p95 > 200 ms
Common causes:
- PostgreSQL is slow / not connected (the cache helps but raw queries dominate). Check that `A2Z_USE_DB=true` and the connection is healthy.
- The API has `--reload` enabled (auto-reload eats CPU). Don't load-test with `uvicorn --reload`. Run `python -m utils.api` cleanly.
- N+1 queries in one of the dashboard endpoints. Profile with
  `EXPLAIN ANALYZE` on the slowest queries.

### `concurrent_users` errors > 2%
Connection pool likely exhausted. Tune `psycopg2.pool.SimpleConnectionPool`
in `utils/db.py` — the default is 1-10 connections. For 1k concurrent
VUs you want ~50-100.

### `export_10k` p95 > 10 s
Either the table actually has > 100k rows (not what we're testing) or
the query plan is bad. Check that `pipeline_deals` has an index on
`open_date` (the default ORDER BY column for the factory).

## CI integration

The repo's CI workflow at `.github/workflows/loadtest.yml` is set to
**manual trigger only** (`workflow_dispatch`). Load tests are too slow
and need a target environment — they don't belong on every push.

To run from GitHub: Actions → "Load test" → Run workflow → pick
target.

The audit gate G19 (added in v5.34) reads `load_results.json` and
enforces the four thresholds. CI's load-test job:
1. Stands up the API with a test database
2. Runs the suite via `scripts/run_load_tests.py`
3. Re-runs `python scripts/audit.py` so G19 sees the artifact

## Operational note

Run a baseline before each release. Compare `load_results.json` to
the previous release's. Regressions (p95 climbing 20%+) get
investigated before the release ships.

A useful shorthand:
```bash
diff <(jq '.tests[]|{test, http_req_duration_p95_ms}' load_results.json) \
     <(jq '.tests[]|{test, http_req_duration_p95_ms}' baselines/last.json)
```
