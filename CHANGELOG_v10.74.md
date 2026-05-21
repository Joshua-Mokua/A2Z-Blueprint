# CHANGELOG v10.74 — ops hygiene drop

**Status:** Single-batch drop. Operational/UX scaffolding alongside the trade_finance arc — does not modify any engine, does not add or activate any standard, does not move audit gate count.
**Audit:** **136/136 PASS** (unchanged from v10.73)
**G117:** 99.0% (195/197) (unchanged)
**G128:** STABLE (340 modules · 871 imports · HARD=3 baseline) (340 vs 338 because of 2 new files: pages/98 + scripts/run_engine_self_tests.py)
**Active standards:** 141/260 (unchanged)
**Scenario library:** 142 (unchanged)

---

## Why this drop is different

Every prior drop in the v10.x sequence has either added an engine, closed an arc, or reconciled a deployment gap. v10.74 is the first **operational hygiene** drop — artifacts that improve the operator experience and tighten the verification feedback loop, without touching any engine code or activating any standard.

The motivation is the deployment-gap reality: nothing is in production at Ecobank yet, the first deployment will likely be a focused pilot of one closed arc, and the closer that pilot gets, the more useful operator-facing scaffolding becomes. A health dashboard, a CI step that catches engine regressions before they ship, and a connection-pooling kit ready to apply when scale matters — these are pre-deployment investments that pay off the moment a real operator touches the platform.

## What this drop ships

### 1. `scripts/run_engine_self_tests.py` — engine self-test orchestrator (~150 lines)

Auto-discovers every `utils/*.py` module that defines a `self_test()` function and runs each. Currently picks up **140 engines**. Per-engine result captures duration + status + stdout + stderr. Two output modes:

- **Default:** human-readable per-engine summary on stderr, exits 0 if all pass / 1 if any fail
- **`--json`:** structured JSON summary on stdout for programmatic consumers

Used by both the new health page and the enhanced CI workflow. Filter flag (`--filter trade_finance`) for targeted runs during development.

The orchestrator adds `REPO_ROOT` to `sys.path` so it works regardless of working directory — important because the health page invokes it via subprocess from inside Streamlit.

### 2. `pages/98_platform_health.py` — operator health dashboard (~280 lines)

Single-page Streamlit dashboard giving operators a 30-second confidence check on whether the platform is in a known-good state. Six tabs:

- **Overview** — three top-level metrics (audit gates, structural integrity, engine self-tests) with green/red status icons and an overall green/red banner. The fastest answer to "is everything okay right now."
- **Audit gates** — runs `scripts/audit.py`, shows passed/total, expandable raw output. Auto-expands the raw output when status is red.
- **Structural integrity** — runs `scripts/structure_audit.py`, shows STABLE/DRIFT plus modules/imports/HARD-finding counts.
- **Engine self-tests** — runs the orchestrator, shows pass/fail per engine in two-column layout, expandable raw output.
- **Standards inventory** — pulls from `STANDARDS_REGISTRY`, breakdowns by subcategory + priority tier. No subprocess — instant.
- **Scenarios inventory** — pulls from `TREASURY_SCENARIO_LIBRARY`, breakdowns by category + scenario family prefix.

Caches subprocess results for 60 seconds via `@st.cache_data(ttl=60)`. Manual `Refresh all checks` button bypasses cache via `cache_data.clear()`.

Uses the existing `require_access()` pattern with module name `platform_health`. Falls back to the `admin` access role when `platform_health` isn't yet registered in `MODULE_ACCESS` — keeps the page discoverable on first deployment without forcing a `MODULE_ACCESS` migration in the same drop.

Calls `audit_log()` on page open and on manual refresh, so platform usage of the health surface is itself auditable.

**Per Rule 7:** the page surfaces health state only. It never auto-fixes violations, never restarts services, never modifies the registry. If a check is red, the operator investigates via the per-tab raw output and applies a remediation drop.

### 3. CI workflow enhancement — `.github/workflows/ci.yml`

Existing CI already runs audit + pytest with coverage + security marker. v10.74 inserts two new steps into the `test` job, between BSC engine self-test and pytest:

- **All engine self-tests** — runs `scripts/run_engine_self_tests.py`, fails build on any engine regression
- **Structural integrity audit** — runs `scripts/structure_audit.py`, fails build on any HARD-baseline drift

These are net-additive; nothing existing was removed or modified. The new orchestrator step alone catches regressions in the 140 auto-discovered engines that the BSC-engine-only step would have missed. With the trade finance arc adding 4 more engines per closure batch, this scaling matters — without the orchestrator, every new engine would need its own explicit step, and pre-merge regressions would slip through silently.

### 4. `deployment/pgbouncer/` — connection pooling deployment kit (~520 lines across 4 files)

Standalone PgBouncer setup that layers with whatever container/host deployment the platform eventually adopts. **Preparatory** — not applied today, but ready when scale demands it.

- `docker-compose.pgbouncer.yml` — PgBouncer service definition using `edoburu/pgbouncer:1.22.1`, configurable via env vars, joins the existing application network.
- `pgbouncer.ini` — runtime configuration with conservative tier-2-bank defaults: transaction pool mode, 25-connection default pool, 500-client max, md5 auth.
- `userlist.txt.template` — credential file template with explicit md5-hash generation instructions. Real `userlist.txt` gitignored.
- `README.md` — when to apply, when not to apply, step-by-step apply procedure, pool-mode caveat (transaction mode breaks session-level prepared statements + LISTEN/NOTIFY), operational notes.

The kit is sized for the actual likely first-deployment scenario at Ecobank: a single Postgres instance handling a Streamlit cluster + FastAPI + occasional ETL. PgBouncer in transaction mode handles this well — A2Z's engines are stateless function calls, the FastAPI handlers don't use session-level prepared statements, the ETL manages its own session affinity. Documented in the README so future drops adding LISTEN/NOTIFY handlers know to route through a separate session-mode pool.

## Verification

All baseline metrics unchanged:
- Audit: 136/136 PASS
- G117: 99.0% (195/197)
- G128: STABLE (340 modules now vs 338, +2 from new files; 871 imports vs 867, +4 from new health page imports)
- Active standards: 141/260
- Scenario library: 142
- Trade finance arc: 4/12 active (in flight, no change this drop)
- All 140 engine self-tests pass via the new orchestrator

## What this does NOT change

- No engine code modified
- No standards activated or deactivated
- No audit gates added (intentional — these are operational artifacts, not engine standards subject to G-gate ratchet)
- No scenarios added
- No Tier 28 changes
- Trade finance arc state unchanged (4/12 active, closes at v10.80)

## Design notes worth preserving

**Why `scripts/run_engine_self_tests.py` instead of pytest plugin.** Pytest collection is heavy when you have 140 engines each defining ~20 internal test functions. A script-based orchestrator that just runs each module's `self_test()` is faster (~3-4 seconds total vs ~15-20 seconds for pytest discovery), produces simpler output (one line per engine vs hundreds of test lines), and integrates naturally with the existing `python -m utils.X` pattern Joshua's engines already use. Pytest still runs the formal tests in `tests/`; the orchestrator runs the engines' own self-tests.

**Why JSON output mode.** The health page invokes the orchestrator via subprocess. Parsing JSON is reliable; parsing free-form text would require regex maintenance. The `--json` flag emits a structured summary on stdout, leaving stderr free for human-readable progress that the page can ignore.

**Why a deployment kit instead of a docker-compose addition.** Joshua's repo doesn't currently have a docker-compose.yml. Adding one would be a much bigger change with implications across the app, ETL, FastAPI tier, etc. Shipping the PgBouncer kit as a standalone overlay means it's there when needed — without imposing a containerization decision on the current architecture.

**Why no audit gate.** G-gate ratchets exist to lock in engine work — they prove an arc closed, an engine activated, a structural baseline held. Operational scaffolding doesn't need a ratchet because it's not subject to silent regression in the same way. The CI workflow itself catches CI-side regressions; the health page catches platform-side regressions; the PgBouncer kit isn't even live yet. Adding G137 for "ops hygiene shipped" would be ratchet padding without value.

## Files changed in this drop

- **NEW** `scripts/run_engine_self_tests.py` (~150 lines)
- **NEW** `pages/98_platform_health.py` (~280 lines)
- **NEW** `deployment/pgbouncer/docker-compose.pgbouncer.yml`
- **NEW** `deployment/pgbouncer/pgbouncer.ini`
- **NEW** `deployment/pgbouncer/userlist.txt.template`
- **NEW** `deployment/pgbouncer/README.md`
- **MOD** `.github/workflows/ci.yml` (2 net-additive steps in `test` job)
- **NEW** `CHANGELOG_v10.74.md` (this file)

## What's next

Trade finance arc resumes at v10.75. ENH-275 Accounting & Integration (IFRS 9 contingent liability journal templates + Basel CCF) + ENH-280 Reporting & Analytics queued as the next dual-batch. Closure batch v10.80 still ~4 drops away.

If a deployment-pilot package becomes a higher priority — minimal Docker compose + focused install guide + Finance arc cockpit + synthetic data seed — that's a separate drop, not interleaved with the engine arc.
