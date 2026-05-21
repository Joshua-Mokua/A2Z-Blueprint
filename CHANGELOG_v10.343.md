# Changelog — v10.343 Schema Lock Extension (Option D sub-batch 2)

**Date:** 2026-05-12
**Phase:** 4 (twenty-eighth arc — D arc continued)
**Audit:** 230/230 gates PASS = 100.0%
**Tests:** 48/48 across the last four batches' suites (plus 707 from earlier batches — full count carries through unchanged)
**G162 Baseline:** 4022 — 37 consecutive zero-drift batches

---

## Your ask

> "we can now continue, the errors were fixed"

Resuming the D → C → E arc. v10.342 was sub-batch 1 (5 files locked). v10.343 = sub-batch 2 — three more high-traffic files now schema-locked.

## What v10.343 added

Eight protected data files total (5 v10.342 + 3 new):

| File | What's locked | Canonical producer |
|---|---|---|
| `kpi_library.json` | 5 canonical top-level keys + nested `kpis` array shape | `pages/7_admin.py` KPI Library tab → `utils/core_kpi.save_kpi_library` |
| `org_hierarchy_config.json` | 6 canonical hierarchy keys (synthetic_top, chiefs, role_tiers, mappings) | admin-editable in `pages/7_admin.py` |
| `pipeline.json` | 10 universal deal fields (id/client_name/staff/product/stage/amount/probability/dates) | `utils/core.py` PipelineManager.save_deal |

Schema lock threshold in G230 strengthened from `≥5` to `≥8`. Adding more in future batches is detected as forward progress; dropping below 8 would fail the gate.

## Real drift surfaced (same pattern as v10.342)

Each of the three pre-existing schema files in `data/_schemas/` had been written speculatively without checking the canonical producer's actual output. Three classes of drift found:

### 1. Pipeline probability — 0-100 percent vs 0-1 fraction

The schema demanded `maximum: 1` for `probability`. The canonical data uses 0-100 percent (302 records, all in 0-100 range). **Schema corrected to match data.**

### 2. kpi_library.direction — four values across two naming conventions

Inspection of all 185 KPIs found:

| Convention | Values | Count | Consumers |
|---|---|---|---|
| Short form | `higher`, `lower` | 88 + 21 | 7 modules |
| Long form | `higher_better`, `lower_better` | 61 + 15 | 2 modules |

The original schema demanded `higher_is_better` / `lower_is_better` — neither convention used in the actual data.

**Decision:** lock all 4 values in the schema (enum accepts all current values), document the divergence in `_known_divergence` metadata as an Option E consolidation candidate. Migrating to a single convention would change consumer behavior in `utils/core.py:6286` and `pages/68_clearing.py:288` — that's not Option D's job.

This is the same pattern as v10.342's strategic_initiatives `rag_status` case: when consumers disagree on canonical form and data has both, schema accepts both and flags it for Option E.

### 3. Org hierarchy `synthetic_top`

The pre-existing schema demanded `synthetic_top` be a string. The canonical data is a dict `{enabled, _note, md}`. Pre-existing schema had already been corrected by an earlier session pass; v10.343 didn't need to touch this — only validates clean now.

## What v10.343 did NOT do

- **Did not migrate kpi.direction values** to a single convention. That's Option E.
- **Did not wire `validate_before_save` into pipeline / kpi_library / org_hierarchy producers.** Those producers are in core.py and 7_admin.py — invasive change. The hook is available for adoption when those producers are touched anyway.
- **Did not touch the 76 KPIs using long-form direction.** They continue working; their consumers (core.py + 68_clearing.py) continue working. Schema documents the situation.

## Files changed

| File | Change |
|---|---|
| `data/_schemas/kpi_library.schema.json` | Direction enum fixed to match actual data; `_known_divergence` metadata added |
| `data/_schemas/pipeline.schema.json` | Probability range corrected to 0-100 percent |
| `data/_schemas/org_hierarchy_config.schema.json` | Validates clean (pre-corrected) |
| `data/_schemas/_README.json` | v10.343 history + file inventory updated |
| `scripts/audit.py` | G230 minimum schema count raised 5 → 8 |
| `tests/integration/test_v10343_schema_lock_extension.py` | NEW — 7 tests |

## Verified outcome

| Metric | Before → After v10.343 |
|---|---|
| Audit gates | 230 → **230** (G230 strengthened, no new gate) |
| Protected data files | 5 → **8** |
| Test suites for last 4 batches | 41 → **48** (+7 v10.343) |
| Known consumer divergences documented | 1 (rag_status) → **2** (+ kpi direction) |
| G162 baseline | 4022 (37 consecutive zero-drift batches) |

## Backlog status

| ID | Status |
|---|---|
| B-009 – B-018 | Open |
| B-027 (tail) | Mostly closed |
| B-028, B-029 | Open |
| B-030, B-034 | Closed |
| B-031, B-032, B-033, B-035, B-036, B-037, B-038 | Open |
| B-039 (page schema drift) | Partially addressed; schema-lock prevents new drift on 8 files |
| B-040 (D arc — lock 3 more schemas) | **Closed v10.343** ✅ |
| B-041 (wire validate_before_save into more producers) | Open |
| B-042 NEW (Option E — consolidate kpi.direction naming) | Documented |
| B-043 NEW (Option E — consolidate rag_status case) | Documented (carried from v10.342) |

## Next direction

D arc has now locked 8 files. The remaining D candidates are smaller / lower-priority. Reasonable next moves:

1. **v10.344 — Move to Option C** — page smoke-test suite. Runtime check that every page opens on the canonical data. Catches the consumer-side bugs your localhost errors surfaced.
2. **v10.344 — Wire `validate_before_save` into more producers (B-041)** — also D, consolidates the protection layer in the admin UIs.
3. **v10.344 — Lock 2-3 more files** (bsc_data.json, mgmt_accounts.json) — continue D incremental.
4. **v10.344 — Verify v10.343 on localhost first** — pause; you extract the zip, confirm everything works, then we continue.

My honest recommendation: **option 1 — move to Option C.** The D arc has covered the highest-traffic drift candidates; remaining files are config-style with lower change frequency. Option C closes the loop on the original "I can't see my progress on localhost" problem — every page gets a runtime check on each batch.

Which way?
