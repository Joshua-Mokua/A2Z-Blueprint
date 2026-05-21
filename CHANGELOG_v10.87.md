# CHANGELOG v10.87 — mlops_persistence helper (post-closure)

**Status:** Post-closure helper module. Sits **alongside** the closed ml_governance arc (closed at v10.86 with G139+G140+G141), not inside it. Provides JSON-file storage helpers that operations uses to persist the three dataclasses the arc engines produce.

**Audit:** 141/141 PASS (unchanged — closure invariants preserved)
**Active standards:** 153/260 (unchanged — helper is not a standard)
**Scenario library:** 186 (unchanged — helper is not engine-architecture)
**Engine self-tests:** 152/152 (was 151; +1 from `mlops_persistence`)
**Structure:** STABLE (355 modules / 922 imports / HARD=3 baseline match)

---

## What this addresses

In the v10.86 closure CHANGELOG honest acknowledgements, I flagged:

> **What's NOT closed and remains operations work**: build the actual JSON/PG persistence layer for the registry, adjudication log, and card archive (engines are stateless; caller stores).

This drop builds the practical default — a pure-stdlib NDJSON helper that operations can use immediately. Same pattern as `utils.core_audit` and other helper modules: caller infrastructure, not engine.

The closed arc invariant is preserved deliberately. The helper:

- Does NOT register a standard in `standards_registry.py` (it's a helper, not Cat B engine work)
- Does NOT modify Tier 29 (which is locked at v10.86 closure)
- Does NOT introduce a new arc subcategory
- Does NOT touch any gate logic
- Does NOT export anything that the mlops_* engines import (engines remain stateless)

It's purely a caller-side utility — same role `utils.core_audit` plays for audit logging.

## What landed

`utils/mlops_persistence.py` (~700 lines, **16/16 tests pass**). Six capabilities, all caller-supplied-data discipline, all Rule 7 caller-side helper:

### File format: NDJSON

Newline-delimited JSON, one record per line. Three properties matter:

1. **Append-friendly** — `f.write(json_line + "\n")`; no read-modify-write cycle
2. **Gap-tolerant** — a single corrupt line doesn't break the file. The loader surfaces corrupt line numbers explicitly per Rule 1, returning the good records alongside.
3. **Operationally inspectable** — `tail -f` shows live appends; `wc -l` counts records; `grep` filters by string match for ad-hoc operations debugging without code

Decimal preservation goes through string round-trip. Enum preservation goes through `.value` round-trip. `Optional[None]` preserved as JSON null. Nested dataclasses (e.g. `ModelCard.production_snapshot: Optional[ProductionPerformanceSnapshot]`) round-trip via nested dicts.

### Six capabilities, paired symmetrically

| # | Capability | Returns |
|---|---|---|
| 1 | `save_registry_entry(path, entry)` | `SaveResult(outcome=SAVED/FAILED, bytes_written, error)` |
| 2 | `load_registry_entries(path, model_id=None, status=None)` | `RegistryLoadResult(entries, total_lines, corrupt_line_numbers, error)` |
| 3 | `save_adjudication_record(path, record)` | `SaveResult` |
| 4 | `load_adjudication_records(path, model_id=None, status=None, after_iso=None, before_iso=None)` | `AdjudicationLoadResult` |
| 5 | `save_model_card(path, card)` | `SaveResult` |
| 6 | `load_model_cards(path, model_id=None)` | `ModelCardLoadResult` |

### Rule 7 boundaries

Helper NEVER:
- Modifies the dataclasses (read-only after engine constructs)
- Decides storage policy (caller chooses path; helper writes)
- Auto-validates against engine output (engine validates at construction; helper trusts what it gets)
- Mutates files outside append-and-read (no delete, no edit-in-place; **retention policy is caller territory** — operations writes a separate purge script using whatever date semantics they need)
- Persists across processes via shared state (each call is a discrete file operation)

### Rule 1 — explicit gap surfacing

Every load returns `total_lines` + `corrupt_line_numbers` tuple. Per Rule 1, operator sees what's broken. A corrupt line at line 47 surfaces as `corrupt_line_numbers=(47,)` — operator can `sed -n '47p' path.ndjson` to inspect, and `sed -i '47d' path.ndjson` to repair if appropriate (caller decides repair policy).

### Save creates parent directories

`save_*` calls automatically create the parent directory tree if it doesn't exist (`os.makedirs(parent, exist_ok=True)`). This is operationally friendly — the first write to a fresh storage directory just works, no separate directory-init step.

## Self-test coverage (16 tests)

Round-trip preservation per dataclass type (3 tests) · `Optional[ProductionPerformanceSnapshot]=None` round-trip · filter by model_id / status / time-window · multiple-filter AND composition · non-existent path returns empty (no error) · corrupt line surfaced with line number · blank line silently skipped · multiple appends grow file · parent directory auto-created · save failure returns explicit error (Rule 1 — never raises silently) · helper doesn't mutate frozen dataclass · path is required parameter (no default — caller must supply).

## Files changed

- **NEW** `utils/mlops_persistence.py` (~700 lines, 16 tests)
- **NEW** `CHANGELOG_v10.87.md` (this file)

## What v10.88 would naturally cover

**Wiring the existing v10.76 hook adopters** (ENH-280 trade_finance_reporting + ENH-270 trade_finance_document_checking) through the persistence layer. The end-to-end demo:

1. Training pipeline calls `MLOpsModelRegistryEngine.register_new_model_version(...)`, gets a `ModelRegistryEntry` with `status=PROPOSED`
2. Pipeline calls `save_registry_entry(REGISTRY_PATH, entry)` to persist
3. Cockpit page (e.g. `pages/97_trade_finance_arc_cockpit.py`) on render calls `load_registry_entries(REGISTRY_PATH, model_id="trade_finance_volume_forecaster")` to surface registered models
4. Operator clicks "promote candidate" → cockpit calls `validate_promotion_readiness`, on READY constructs new entry with `status=ACTIVE` (using `dataclasses.replace`), saves new entry to registry
5. Old entry's `status` doesn't change in-place (NDJSON is append-only) — instead, the new entry supersedes when the lookup picks the most recent ACTIVE per model_id

That last bullet is interesting — NDJSON's append-only nature means status changes are **new records** rather than mutations. `lookup_active_version` already handles this correctly: it filters by model_id + status=ACTIVE and surfaces multiple_active_violation when more than one matches. Operations sees the breach if status changes overlap — exactly the audit story we want.

Plus: capturing operator override decisions via `save_adjudication_record` in the discrepancy-checking inference path. Plus: cockpit-page tabs for browsing registry + adjudication archive. Plus: optionally, a small `pages/_mlops_paths.py` that centralizes the conventional storage paths so all callers agree on `REGISTRY_PATH`, `ADJUDICATION_PATH`, `CARD_ARCHIVE_PATH`.

That's the v10.88 single-batch scope. After it ships, the MLOPS_INTEGRATION_REGISTRY's `*_wiring_planned: True` claims for ENH-280 and ENH-270 become **actually wired** — and a future G142 enhancement could add a `*_wiring_actual: bool` field that flips True after verification.

## Honest acknowledgements

**NDJSON is the only format.** No JSON-array, no SQLite, no PG. JSON-array would need read-modify-write per save (slow for high-frequency adjudication append). SQLite would add a binary file format that doesn't `tail -f` cleanly. PG would couple operations to a database server. NDJSON is the simplest defensible default. Future enhancement could add a parallel `mlops_persistence_pg.py` with the same six-capability interface backed by Postgres — caller swaps the import without changing call sites.

**No transactional guarantees.** Two concurrent `save_*` calls to the same path could interleave bytes if both crossed an OS write boundary mid-line. For typical ops volume (hundreds of saves per day), this is fine. For high-volume async pipelines, caller should serialize writes through a queue or use a real DB. Documented as caller responsibility.

**No file rotation.** A registry NDJSON file grows monotonically. After 5 years of weekly registrations, the file would have a few hundred lines — not a problem. The adjudication log could grow to millions of lines depending on inference volume; operations would need to archive old data periodically. The helper provides no rotation primitive — that's a separate ops concern. A future enhancement could add `archive_records_older_than(path, archive_path, before_iso)` that moves matching records to an archive file. Not in this drop.

**Time-window filters use lexicographic comparison on ISO 8601.** Works correctly for properly-formatted ISO 8601 with consistent offset (e.g. all "Z" suffixes or all "+03:00" suffixes). Mixed offsets in the same file would compare incorrectly. Documented as caller convention: pick one offset format and stick with it across the file.

**No filter for `card_version` or `composed_by` on cards.** The `load_model_cards` filter is just `model_id`. If callers want to filter by `card_version` or `composed_by`, they iterate the result tuple. Adding more filter params is a future enhancement when there's a use case.

**Reverse chronological sort not provided.** Loader returns records in file-append order (which is approximately chronological if callers append in real time). For "most-recent-first" display, caller does `tuple(reversed(records))`. Adding a `sort_order` param is a future enhancement.

**Helper is not in any tier.** Tier 29 is locked at closure. Tier 30 doesn't exist (yet). The helper file just lives in `utils/` and is documented in this CHANGELOG. Future arcs that produce platform infrastructure consumed by callers (rather than other engines) might warrant a "Helpers" tier — but creating one for a single module is overkill.

**No standard ID.** Helpers don't fit the Standard pattern — they're not Cat A or Cat B engine work, they're caller infrastructure. Adding a standard would force a subcategory choice that doesn't naturally fit (`ml_governance` is closed; `helper` doesn't exist as a subcategory). Documented existence is sufficient. The audit ratchet doesn't enforce 1:1 between utils/ files and standards anyway — many helper modules (core_audit, etc) exist without standards entries.

---

Cleared to proceed to v10.88 — the actual wiring of ENH-280 + ENH-270 through ENH-281+282+285 in the trade_finance cockpit page — when ready.
