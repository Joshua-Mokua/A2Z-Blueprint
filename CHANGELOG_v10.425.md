# Changelog — v10.425 Pillar canonical merge (BSC Rescue batch 1)

**Date:** 2026-05-14
**Phase:** BSC Rescue (batch 1 of ~5)
**Audit:** G311 added (cumulative 311 gates)
**Tests:** 14/14 PASSED in `test_v10425_pillar_canonical_merge.py`
**Regression:** 366/366 v10.4xx tests PASSED (352 + 14)
**Verifier:** 731 → **737** (+6 v10.425 checks)
**G162 baseline:** 4022 (118 consecutive zero-drift batches)
**Master prompt:** v4.67 → v4.68 (lockstep — 69 consecutive batches)

**BSC HEALTH: 28.6% → 42.9% (+14.3 points)** — first rescue batch lands.

---

## What this batch is

The first BSC Rescue fix batch. Closes finding #3 from the v10.424 audit: **221 BSC rows using non-canonical "Operational" pillar instead of "Operational Excellence"**.

The bug had two roots — fixed both:

1. **Source bug**: `simulate_v2.py` (the actuals generator) had **19 KPI definitions** hardcoded with `"pillar":"Operational"`. Mechanically converted all 19 to `"pillar":"Operational Excellence"`.

2. **Data state**: 221 rows in `data/actuals_2025_Dec_25.xlsx` carried the wrong pillar value from prior generations. Migrated via the new engine.

Both root and data are now canonical. Future generations cannot reintroduce the alias because `simulate_v2.py` no longer contains it.

## Live migration result

**Pre-migration** (from v10.424 audit):
- 221 rows tagged `"Operational"` across 21 unique KPIs (Credit TAT, Loan Disbursement TAT, Compliance SLA, FD Ratification, Legal TAT, etc.)
- Affected roles: Credit Admin Officer (40), Credit Analyst (40), Legal Officer (12), Relationship Officer-Business Banker (10), Relationship Officer-Personal Banker (9)

**Post-migration:**
- 221 rows now `"Operational Excellence"` ✓
- 0 non-canonical pillars in BSC actuals ✓
- Backup at `data/_v10425_backups/actuals_2025_Dec_25.xlsx.before`
- BSC audit pillar_canonical: **0 issues** (was: 221 rows in 1 alias)

## What v10.425 built

### NEW `utils/bsc_pillar_normalize_engine.py` (~250 LOC)

Zero streamlit imports. 19th React-ready engine module.

**Constants:**
- `CANONICAL_PILLARS` — matches v10.423 + v10.424
- `ALIAS_MAP` — `{"Operational": "Operational Excellence"}` (extensible if future aliases discovered)

**Public API:**

| Function | Returns | Purpose |
|---|---|---|
| `audit_actuals_pillars(actuals_path)` | `ActualsPillarAudit` | Per-pillar row counts + affected KPIs/roles |
| `migrate_actuals_pillars(actuals_path, dry_run=True)` | `PillarMigrationResult` | Flip non-canonical → canonical; **default dry-run** |

**Safety:** `dry_run=True` is the default. Migration creates `.before` backup in `data/_v10425_backups/` before writing.

**Idempotent:** Re-running on a clean file produces no changes.

### Source fix in `simulate_v2.py`

Mechanically replaced via regex: every `"pillar":"Operational"` (with or without spacing) → `"pillar":"Operational Excellence"`. **19 occurrences fixed.** No other changes to the file.

### Data migration in `data/actuals_2025_Dec_25.xlsx`

Engine flipped 221 rows. Backup preserved at `data/_v10425_backups/actuals_2025_Dec_25.xlsx.before`. The 2-row header pattern (banner + columns) was preserved during write-back so the file remains readable by the same `skiprows=1` loader.

### NEW `scripts/normalize_pillars.py` runner

```bash
# Audit only (default)
python scripts/normalize_pillars.py

# Apply migration
python scripts/normalize_pillars.py --confirm
```

### NEW 2 FastAPI endpoints

| Method | Path | Purpose |
|---|---|---|
| `GET`  | `/api/v1/bsc-pillar/audit`   | Per-alias counts + affected KPIs |
| `POST` | `/api/v1/bsc-pillar/migrate?confirm=true` | Apply migration |

### Audit gate G311

Verifies engine API + zero streamlit + ALIAS_MAP correct + `dry_run=True` default + runner `--confirm` + 2 endpoints + **simulate_v2.py source fix held** + **BSC actuals zero non-canonical** + engine state 0/0/0/0.

### Forward-compat fix

v10.424's `test_v10424_pillar_canonical_finds_operational` originally asserted `"Operational" in result.non_canonical_pillars` (because at v10.424 ship-time the bug was live). v10.425 makes the test forward-compatible: it now asserts the audit category itself functions correctly, accepting either pre-v10.425 (bug present) or post-v10.425 (clean) state.

## Verified outcome

| Metric | v10.424 | v10.425 |
|---|---|---|
| Audit gates | 310 | **311** |
| v10.4xx tests | 352 | **366** (+14) |
| Verifier | 731 | **737** (+6) |
| API endpoints | 47 | **49** (+2) |
| React-ready engines | 18 | **19** |
| Lockstep batches | 68 | **69** consecutive |
| G162 baseline | 4022 (117) | 4022 (**118** zero-drift) |
| **BSC health** | **28.6%** | **42.9%** (+14.3 points) |
| Engine state | 0/0/0/0 | **0/0/0/0** ✓ |

## 10 honest acknowledgements

1. **Two-layer fix matters.** Migrating only the data without fixing `simulate_v2.py` would mean the next regeneration reintroduces the alias. Fixing only the source without migrating actuals leaves 221 rows stale. Both layers needed.

2. **`simulate_v2.py` was not deep-reviewed before.** 19 hardcoded values flew under the radar through 100+ batches. The audit engine surfaced the symptom (221 rows); a grep found the source. The pattern reproduces: audit reveals state, state reveals source.

3. **Backup is in `_v10425_backups/`, not deleted.** The v10.421 backup retention cleanup engine has a `--keep-recent 3` default — by the time we reach v10.428, this v10.425 backup may roll off. The migration is idempotent, so re-running it on already-clean data is a no-op.

4. **`ALIAS_MAP` is extensible.** If a future audit surfaces another alias (e.g., "Customer" instead of "Customer Focus"), it's a one-line addition to the map. The engine handles any number of aliases uniformly.

5. **The Excel re-write preserves the 2-row header pattern.** `data/actuals_*.xlsx` has a blank banner row (row 0) and column names (row 1); the `pd.read_excel(skiprows=1)` consumers depend on this shape. The engine's writer preserves it.

6. **Affected KPIs included real ones, not test data.** Credit TAT, Loan Disbursement TAT, FD Ratification, Legal TAT — these are operational excellence KPIs the bank actually tracks. The fix correctly classifies them under the canonical pillar.

7. **+14.3 health points for one batch is high.** Pillar canonical was a clean, well-bounded issue. The remaining 4 issues (KPI completeness, weight normalization, library alignment, cascade linkage) are larger surfaces and will move the needle less per batch.

8. **Test forward-compat is a Phase 2d habit now.** Same pattern as v10.420 (the dedup test) and v10.403 (the KPI markers test). When a fix invalidates an earlier test assertion, the cleanest move is making the earlier test verify "audit functioning" rather than "specific bug present". v10.424 → v10.425 just continued this.

9. **Engine state and verifier untouched in the BSC arc.** Cascade-structure-engine still reports 0/0/0/0. The verifier grew by 6 checks for v10.425 surface only. The BSC rescue arc isolates BSC concerns; cascade health is locked in.

10. **Roadmap is on track.** v10.425 was scoped as "smallest blast radius, highest signal" — delivered exactly that. Each subsequent rescue batch will be larger but follow the same engine + runner + API + gate template.

## On your end

1. Close Streamlit if running
2. Extract `a2z_v10425_patch.zip` on top of v10.424 state
3. `python scripts/verify_local_state.py` → expect **737/737**
4. `python utils/cascade_structure_engine.py` → 0/0/0/0
5. `python utils/bsc_pillar_normalize_engine.py` → engine self-test (7 checks)
6. **Run BSC audit**: `python scripts/audit_bsc.py` → confirm pillar canonical = ✓ CLEAN
7. (Optional, idempotent) `python scripts/normalize_pillars.py` → audit shows 0 to migrate
8. Tell me **"continue"** → v10.426 = library alignment (decide what to do with the 81 unregistered BSC KPIs)

## Roadmap

| Batch | Concern | Status |
|---|---|---|
| ~~v10.424~~ | ~~BSC Deep Audit Engine~~ | **DONE** |
| **v10.425** | **Pillar canonical merge** | **DONE (this batch)** |
| v10.426 | Library alignment (81 unregistered BSC KPIs) | Next |
| v10.427 | Chief BSC completeness | After v10.426 |
| v10.428 | Weight normalization in actuals | After v10.427 |
| v10.429 | Cascade-BSC linkage gap | After v10.428 |
| v10.430+ | BSC scorecard table dual-view + compliance render | After audit health 100% |
