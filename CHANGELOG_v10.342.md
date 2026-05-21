# Changelog — v10.342 Data Schema Lock (Option D)

**Date:** 2026-05-12
**Phase:** 4 (twenty-seventh arc — Option D harmonization, foundation layer)
**Audit:** 230/230 gates PASS = 100.0%
**Tests:** 755/755 passing across 46 integration suites (14 new for v10.342)
**G162 Baseline:** 4022 — 36 consecutive zero-drift batches

---

## Your ask

> "D → C → E in that order. hope this ensure that the code does not drastically change what it is supposed to perform?"

After my confirmation that D is safe by construction (same values, consistent shape, reversible per file), you said "continue." v10.342 is Option D, sub-batch 1.

## What v10.342 delivered

The foundation layer for harmonization — every protected data file now has a locked JSON Schema, and a fail-closed validator gates future writes. Five files locked this batch:

| File | What's locked | Canonical producer |
|---|---|---|
| `bank_targets.json` | dict-of-`{target, buffer_pct}` (already cleaned v10.341) | `pages/12_cascade.py` Bank Targets editor |
| `cost_allocation_rules.json` | rule list with method + drivers + weights | `pages/7_admin.py` → Performance → Cost Matrix |
| `execute_initiatives.json` | 5 required fields + optional metadata allowed | `pages/4_execute.py` initiative manager |
| `segment_config.json` | Individual/Business/CBK/propositions structure | `pages/7_admin.py` → Performance → Segment Configuration |
| `strategic_initiatives.json` | 31 universal fields, Title-case `rag_status`, int counts | `pages/83_strategy.py` |

### New module — `utils/schema_validator.py`

Pure-stdlib JSON Schema validator (no `jsonschema` dependency). Implements the subset needed by our schemas:

`type` | `required` | `properties` | `additionalProperties` | `items` | `enum` | `pattern` | `oneOf` | `minItems` | `maxItems` | `minLength` | `minimum` | `maximum`

Public API:
- `list_protected_files()` → filenames with registered schemas
- `load_schema(filename)` → schema dict
- `validate_file(filename)` → {valid, errors, schema_version, protected}
- `validate_all_protected()` → batch summary
- `validate_before_save(filename, value)` → producer hook (fail-closed)
- `validate_value(value, schema)` → low-level

170 lines, pure stdlib. The subset omits `$ref`, `allOf`, `anyOf`, `not`, `format` — none of those were needed by the five schemas. If a future schema needs them, expand the validator with tests; the surface is intentionally minimal.

### New audit gate G230 — data_schema_lock

Runs `validate_all_protected()` every audit run. Any file failing its schema raises a violation. Currently 5/5 valid; future drift fails the gate before it lands.

### Producer hook wired into `cost_allocation.save_rules`

`utils.cost_allocation.save_rules` now runs `validate_before_save("cost_allocation_rules.json", blob)` before writing. If the payload doesn't match the schema, the save is refused and the admin UI surfaces the error. Existing `validate_rule` from v5.49 still runs first (catches obvious issues); schema lock is the second line of defence.

Other producers (`pages/83_strategy.py` for strategic_initiatives, `pages/12_cascade.py` for bank_targets) aren't yet wired through `validate_before_save` — adding that without explicit direction would be exactly the layering pattern v10.341 flagged. The hook is available; the producers can adopt it batch-by-batch.

### Real drift surfaced (and resolved correctly)

During schema authoring, the validator caught two actual data-vs-code divergences in `strategic_initiatives.json`:

1. **`rag_status` case mismatch.** My first schema demanded UPPERCASE (`GREEN/AMBER/RED`). The 25 records in the file use Title case (`Green/Amber/Red`). Three consumers tell different stories:
   - `pages/83_strategy.py` (canonical producer) writes Title case
   - `utils/strategy_health.py` reads Title case ✓
   - `utils/command_centre_strategic_initiatives.py` expects UPPERCASE — diverges

   **Locked Title case as canonical** (matches data + canonical producer). The divergent module's mismatch is tagged in the schema's `_consumers_must_tolerate_missing` metadata and is an Option E concern.

2. **Three "array" fields are actually int counts.** `linked_projects`, `key_milestones`, `stakeholders` hold integers (counts), not arrays. The canonical producer writes them as ints (`pages/83_strategy.py` line 128: `"linked_projects": 0`). My schema was wrong; the data is canonical. Fixed the schema.

These weren't my bugs from this batch — they were existing drift that the validator made visible. Exactly what Option D is supposed to do.

### What I deliberately did NOT do

Per the conversation in v10.341 about not adding layers without direction:

- **Did not patch `command_centre_strategic_initiatives.py`** to use Title case. That's a producer/consumer schema reconciliation question for Option E.
- **Did not migrate `bsc_actuals_*.json` schemas.** Those carry intentional optionality across 9 producers — locking them prematurely would force every producer to fill every field, which defeats the design. They're candidates for a separate schema in a later D sub-batch with consumer-side requirements documented.
- **Did not auto-wire `validate_before_save` into every producer.** That's invasive cross-cutting change. The hook exists; producers adopt it explicitly per future batch when the producer is being touched anyway.

## Verified outcome

| Metric | Before → After v10.342 |
|---|---|
| Audit gates | 229 → **230** (G230 added) |
| Integration test suites | 45 → **46** |
| Tests passing | 741 → **755** (+14) |
| Protected data files | 0 → **5** |
| Schemas in `data/_schemas/` | 0 → **5 + README** |
| `validate_before_save` producer hooks | 0 → **1** (cost_allocation) |
| Real drift surfaced + locked | 2 (rag_status case + 3 count fields) |
| G162 baseline | 4022 (36 consecutive zero-drift batches) |

## Architecture compliance

- **G2 (direct I/O).** First version of schema_validator used `path.read_text()` directly. Caught immediately by audit. Refactored to `utils.db.db.load_json`. Zero violations.
- **G162 (tenant identity).** Schemas live in `data/_schemas/` and describe shape, not tenant identity. No KES/CBK/Kenya/FLEXCUBE/KRA tokens. Baseline unchanged.
- **G117 (engine hub coverage).** `schema_validator` is a quality-gate utility, not a customer-data engine — doesn't go in ENGINE_HUB_TIERS (the existing pattern is reserved for KPI / P&L / customer engines). G117 still green at 95.5%.

## Files changed

| File | Change |
|---|---|
| `data/_schemas/_README.json` | NEW — documents the schema-lock pattern + history |
| `data/_schemas/bank_targets.schema.json` | NEW — locks v10.341 cleaned shape |
| `data/_schemas/cost_allocation_rules.schema.json` | NEW — locks v10.339 rule shape |
| `data/_schemas/execute_initiatives.schema.json` | NEW — locks 5-field minimum |
| `data/_schemas/segment_config.schema.json` | NEW — locks v10.338 canonical vocabulary |
| `data/_schemas/strategic_initiatives.schema.json` | NEW — locks 31-field canonical producer shape |
| `utils/schema_validator.py` | NEW — 280 lines, pure-stdlib JSON Schema subset |
| `utils/cost_allocation.py` | `save_rules` now calls `validate_before_save` (fail-closed) |
| `scripts/audit.py` | NEW `gate_data_schema_lock` + G230 registration |
| `tests/integration/test_v10342_schema_lock.py` | NEW — 14 tests across 4 sections |

## What's next in the D arc

This sub-batch locked 5 files. The data inventory found ~68 files with shape variation. Most are intentional polymorphism (config files with deliberately mixed top-level keys, not record drift). The remaining drift candidates I'd consider for sub-batches in this arc:

- **`kpi_library.json`** — drift-prone history (v10.337 patch issues). Worth its own schema.
- **`org_hierarchy_config.json`** — central, widely-consumed. Lock the canonical hierarchy structure.
- **`pipeline.json`** — 302 deals with 34 optional fields. Lock minimum + permitted optional.
- **`bsc_actuals_*.json`** — quarterly aggregates with intentional optionality. Schema would document which fields each producer must fill.

But before continuing the D arc — **does this batch land cleanly on your localhost:8501?** I'd want to verify the schema-lock hook doesn't surface unexpected issues in production before locking more files. v10.343 should wait on your read.

## Backlog status

| ID | Status |
|---|---|
| B-023, B-025, B-026 | Open |
| B-027 | Mostly closed v10.337 |
| B-028, B-029 | Open |
| B-030, B-034 | Closed |
| B-031, B-032, B-033 | Open |
| B-035, B-036, B-037, B-038 | Open |
| B-039 (page schema drift) | Partially addressed — 4 of 10 fixed v10.341; schema-lock prevents new drift; remaining 6 still latent |
| B-040 (NEW) | **D arc — lock kpi_library + org_hierarchy + pipeline schemas** |
| B-041 (NEW) | **D arc — wire validate_before_save into pages/83_strategy + pages/12_cascade producers** |
| B-009 – B-018 | Open |

## Suggested next direction

The harmonization arc is **D → C → E**. v10.342 was D sub-batch 1. Options:

1. **v10.343 — D sub-batch 2** — lock 3-4 more high-traffic schemas (`kpi_library`, `org_hierarchy_config`, `pipeline`). Continue the D arc.
2. **v10.343 — Wire validate_before_save into more producers (B-041)** — also D, but consolidates the protection layer.
3. **v10.343 — Move to Option C** — page smoke-test suite. Catches the consumer-side bugs the v10.341 fixes addressed.
4. **v10.343 — Verify v10.342 on localhost first** — pause; you extract the zip, confirm `localhost:8501` works, then we continue.

My honest recommendation: **option 4 — verify on localhost first**. The schema-lock pattern is new infrastructure; better to confirm it doesn't surface anything on your end before locking more files.

What's the direction?
