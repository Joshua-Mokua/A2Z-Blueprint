# Changelog — v10.474 Phase O8 Environment Isolation Governance

**Date:** 2026-05-15
**Doctrine source:** *Master Prompt — Enterprise Banking Digital Twin Phase O8*
**Joshua mandate:** *"No simulation artifacts may contaminate production DNA."*
**Audit:** G360 added (cumulative **392 gates**)
**Tests:** 23/23 v10.474 integration tests PASS
**Combined regression:** 1182+ v10.4xx tests
**Verifier:** 1019 → **1027** (+8 v10.474 checks)
**G162 baseline:** 4022 (**168 consecutive** zero-drift batches)
**Master prompt:** v5.17 → v5.18 (lockstep — **119 consecutive batches**)

---

## Why O8 now, not last

The Master Prompt lists O8 as the eighth Olympic phase. We pulled it forward to second position because every subsequent batch (O2 telemetry, O3 channel simulators, O4 macro events, O5 chaos, O6 AI evolution, O7 training) **generates simulation artefacts**. Without the isolation boundary locked first, simulation DNA contaminates `data/` for 12 batches — a debt we'd have to repay later.

Lock the boundary now. Build everything else into the boundary.

---

## 🎯 What the boundary looks like

```
                ╔════════════════════════════════════╗
                ║   PRODUCTION                       ║
                ║   data/users.json, kpi_library, etc║
                ║   PROTECTED — no SIM/UAT writes    ║
                ╚════════════════════════════════════╝
                            ▲
                            │ promote (one-way, audit-logged)
                            │
        ╔═══════════════════════════════════╗
        ║   STAGING — data/staging/         ║
        ╚═══════════════════════════════════╝
                            ▲
                            │
   ┌────────────────────────┴─────────────────────────┐
   │                                                  │
╔═══════════════╗                            ╔═══════════════╗
║  UAT          ║                            ║  SIM          ║
║  data/uat/    ║◄─────── promote ───────────║  data/sim/    ║
║  disposable   ║                            ║  disposable   ║
╚═══════════════╝                            ╚═══════════════╝
        ▲                                            ▲
        │                                            │
        └──────────────── DEV ───────────────────────┘
                       (local clone)
```

**Demotions forbidden.** PROD is terminal. There is no `PROD → DEV`, no `STAGING → SIM`. Anything that wants to flow backward must be re-created from source.

---

## Eight components shipped

### 1. `utils/environment.py` (NEW) — canonical mode declaration

```python
class Environment(str, Enum):
    DEV = "dev"
    SIM = "sim"
    UAT = "uat"
    STAGING = "staging"
    PROD = "prod"

ALLOWED_PROMOTIONS = {
    Environment.DEV:     {Environment.SIM, Environment.UAT},
    Environment.SIM:     {Environment.UAT},
    Environment.UAT:     {Environment.STAGING},
    Environment.STAGING: {Environment.PROD},
    Environment.PROD:    set(),  # terminal
}
```

Resolution order: `A2Z_ENV` env var → `data/environment.json` → default `DEV`.

Public API: `get_environment()`, `set_environment(target, set_by, reason, force=False)`, `is_production()`, `is_simulation()`, `is_staging()`, `is_uat()`, `is_dev()`, `environment_paths()`.

### 2. `data/environment.json` (NEW)

Canonical mode state. Default `dev`. Production deployments must explicitly set `A2Z_ENV=prod`.

### 3. `utils/data_isolation_guard.py` (NEW) — write-side guard

```python
PROTECTED_PROD_FILES = {
    "data/users.json", "data/hr.json", "data/kpi_library.json",
    "data/target_cascade.json", "data/bank_targets.json",
    "data/bsc_scores.json", "data/actuals_yoy.json",
}
```

API:
- `guarded_write_path(rel)` — returns the mode-appropriate absolute path. SIM → `data/sim/<rel>`; PROD → `data/<rel>`.
- `is_write_allowed(path, mode=None)` → `(bool, reason)`
- `is_protected_production_path(path)` → bool
- `assert_not_production(operation)` — raises `RuntimeError` in PROD (used for chaos-mode-only operations)
- `audit_summary()` — snapshot of isolation posture

### 4. `utils/data_migration.py` (NEW) — promotion helper

```python
promote_dataset(
    src=Environment.SIM, dst=Environment.UAT,
    actor="300011", reason="...",
    file_filter=["bsc_actuals_2026-Q1.json"],
    dry_run=False,
) -> PromotionResult
```

- Honours the one-way ladder via `ALLOWED_PROMOTIONS`
- Dry-run default (preview only)
- Audit-logged via `utils.audit_log` (severity `critical` for PROD-destination)
- `list_environment_inventory(env)` for pre-promotion diff

### 5-7. Sandbox directories with READMEs

- `data/sim/README.md` — disposable simulation outputs
- `data/uat/README.md` — UAT cycle outputs
- `data/staging/README.md` — pre-prod rehearsal
- `cbs_data/sim/`, `cbs_data/uat/`, `cbs_data/staging/` — mirrored CBS roots

### 8. `docs/environment_isolation_policy.md` (NEW)

The governance doctrine: 5 environments, promotion ladder, protected files, audit evidence, onboarding checklist for new write-side engines.

### Wired into `utils/vb_actuals_bridge.py`

The bridge now consults `is_write_allowed()` before live writes. In SIM/UAT/STAGING modes, attempts to write live BSC actuals are blocked with a clear error pointing the user to `set_environment(PROD)` or `dry_run=True`.

---

## G360 — locks Phase O8

G360 verifies on every audit run:
1. `utils/environment.py` exists with `Environment` enum + `get_environment` + `set_environment` + `ALLOWED_PROMOTIONS` + `environment_paths`
2. `data/environment.json` declares a valid mode
3. `utils/data_isolation_guard.py` exposes the full API
4. `utils/data_migration.py` exposes `promote_dataset` + `list_environment_inventory`
5. `data/sim/`, `data/uat/`, `data/staging/` exist each with `README.md`
6. `docs/environment_isolation_policy.md` exists with all 5 env names + key APIs + `PROTECTED` keyword
7. `vb_actuals_bridge.py` wires the guard
8. `ALLOWED_PROMOTIONS[PROD]` is empty (terminal)
9. Mechanical smoke test: `promote_dataset(PROD → DEV)` is refused
10. Prior cert (G354/G355/G356/G357/G358/G359) preserved

**G360 currently PASSES.**

---

## Verified outcome

| Metric | v10.473 | v10.474 |
|---|---|---|
| Audit gates | 391 | **392** (G360) |
| Verifier | 1019 | **1027** (+8) |
| Lockstep batches | 118 | **119** |
| G162 baseline | 4022 (167) | 4022 (**168** zero-drift) |
| **Phase O1** | LOCKED | LOCKED ✓ |
| **Phase O8** | n/a | **LOCKED** ✅ |
| Environment enum | absent | **5 modes (DEV/SIM/UAT/STAGING/PROD)** |
| `environment.json` | absent | **present (default dev)** |
| `guarded_write_path` | absent | **present** |
| `promote_dataset` | absent | **present** (one-way audit-logged) |
| Sandbox dirs | absent | **3 (sim/uat/staging) + 3 cbs sandboxes** |
| Policy doc | absent | **present** |
| PROD→DEV demotion attempt | not protected | **mechanically refused** |
| All prior cert (G354-359) | preserved | preserved ✓ |

---

## On your end

1. Extract `a2z_v10474_patch.zip` on v10.473 (overwrite all)
2. `python scripts/verify_local_state.py` → **1027/1027**
3. `python scripts/audit.py` → **392/392**
4. **Check the current mode** (should default to `dev`):
   ```python
   from utils.environment import get_environment
   print(get_environment().value)  # → 'dev'
   ```
5. **Try a guarded write path** (no actual write):
   ```python
   from utils.data_isolation_guard import guarded_write_path
   from utils.environment import Environment
   print(guarded_write_path("bsc_actuals_2026-Q1.json", mode=Environment.SIM))
   # → /path/to/data/sim/bsc_actuals_2026-Q1.json
   print(guarded_write_path("bsc_actuals_2026-Q1.json", mode=Environment.PROD))
   # → /path/to/data/bsc_actuals_2026-Q1.json
   ```
6. **Try a forbidden write** (should be blocked):
   ```python
   from utils.data_isolation_guard import is_write_allowed
   from utils.environment import Environment
   print(is_write_allowed("data/users.json", mode=Environment.SIM))
   # → (False, "mode=sim cannot write to protected production path data/users.json...")
   ```
7. **Try a demotion** (should be refused):
   ```python
   from utils.data_migration import promote_dataset
   from utils.environment import Environment
   r = promote_dataset(src=Environment.PROD, dst=Environment.DEV,
                       actor="me", reason="testing", dry_run=True)
   print(r.error)  # → "promotion prod -> dev not in allowed set []"
   ```

---

## What this unlocks

With O1 (wiring) and O8 (isolation) both locked, the body is safe for **Phase O2 — Truth, Telemetry & Observability** in v10.475.

Roadmap progression:
- ✅ **v10.473** O1 Stabilization — wiring sound
- ✅ **v10.474** O8 Isolation — boundary locked (THIS BATCH)
- ⏭️ **v10.475** O2-A — Event tracing + lineage + workflow replay
- **v10.476** O2-B — AI explainability + operational heatmaps + anomaly observability
- **v10.477-479** O3 — Channel simulators (RTGS/SWIFT/ATM/USSD/M-Pesa/KIC/Cards) + scenarios → 100+
- **v10.480-481** O4 — Time evolution + macro economic simulation
- **v10.482** O5 — Chaos engineering
- **v10.483-484** O6 — AI/ML/LLM evolution lab
- **v10.485-486** O7 — Training arena (roles, drills, tournaments)
- **v10.487** Olympic-Grade certification
- **v10.488+** Track C — React facelift

---

## 🏥 Patient status

The patient now lives in a building with **clearly marked rooms** — sim ward, UAT ward, staging ward, production ward. The doors only open one way (toward production). The protected vault is sealed.

Now we can safely build the nervous system upgrade (Phase O2) without risk of stray simulation signals leaking into production telemetry.

**Tell me "continue"** for v10.475 — Phase O2-A (Truth, Telemetry & Observability — event tracing + lineage + workflow replay).
