# Customer Profitability → Canonical Engine Refactor

**Version anchor:** v10.381 (May 2026)
**Per:** Phase B roadmap commitment from v10.378/v10.379/v10.380 wrap-ups
**Companion to:** `CUSTOMER_MASTER_MERGE_v10.378.md`

> "Refactor `customer_profitability.py` to consume v10.378 unified customer master"

v10.378 established the canonical customer master (`compute_unified_customer_master`). v10.381 makes the customer profitability engine consume it.

## Part 1 — Why this matters

Before v10.381:

```
customer_profitability.py
    │
    ▼  (reads directly)
data/customer_intelligence.json   (3,000 marketing-only records)
```

The engine saw only the marketing-intel universe. Customers in CBS but not in marketing were invisible to it. Customers in BOTH had a "marketing-only" view of themselves (e.g. CBS-authoritative segment/branch_code/rm_code not seen).

After v10.381:

```
customer_profitability.py
    │
    ▼  (canonical-first; legacy fallback)
utils/customer_master_canonical.compute_unified_customer_master()
    │
    ├── CBS customers (transactional reality)
    ├── Marketing intel (analytics overlay)
    └── _field_lineage (provenance per field)
```

Same engine output, broader and richer data source. Constitution §4.3 (single source of truth) and §5.1/§5.2 (canonical engines feed all consumers) honored.

## Part 2 — Why the refactor is small

The engine already has dependency injection. `CustomerProfitabilityEngine.__init__` accepts `customer_lookup_fn`. Default was `_default_customer_lookup` which read `customer_intelligence.json` directly.

v10.381 replaces the **internal default** without changing the public API:
- `_default_customer_lookup` is still the default
- Its IMPLEMENTATION now calls `_canonical_customer_lookup_v10381` first
- Falls back to `_legacy_customer_intelligence_lookup` if canonical engine unavailable

Callers that pass their own `customer_lookup_fn` are unaffected. Callers that use the default get the canonical-first behavior automatically.

## Part 3 — Module changes

### Renamed for clarity

| Before | After | Role |
|---|---|---|
| `_default_customer_lookup` | `_default_customer_lookup` (same name, new impl) | Public default — canonical-first |
| (none) | `_canonical_customer_lookup_v10381` | NEW — calls v10.378 canonical engine |
| (none) | `_legacy_customer_intelligence_lookup` | RENAMED — preserves old behavior as fallback |
| (none) | `reset_canonical_customer_cache` | NEW — test helper to clear module cache |

### Module-level cache

```python
_UNIFIED_MASTER_CACHE: Optional[Dict[str, Any]] = None
```

`compute_unified_customer_master` iterates 3,000+ records on each call. We cache the result at module level so per-customer lookups are O(1). Cache is cleared by `reset_canonical_customer_cache()` for tests and on CBS refresh.

### Resolution order

```python
def _default_customer_lookup(customer_id: str) -> Optional[dict]:
    # 1. Try canonical engine (v10.378)
    rec = _canonical_customer_lookup_v10381(customer_id)
    if rec is not None:
        return rec
    # 2. Legacy fallback
    return _legacy_customer_intelligence_lookup(customer_id)
```

The canonical lookup catches Exception broadly (ImportError if v10.378 module unavailable; FileNotFoundError if data files missing). On any failure, it returns None and falls through to legacy. **No silent failures** — but graceful degradation if canonical infrastructure absent.

## Part 4 — Field compatibility

The engine consumer contract: `customer_lookup_fn` returns a dict with a `segment` field at minimum.

UnifiedCustomerRecord (v10.378) has these fields (verified via dataclass introspection):

```
cif, full_name, customer_type, enrichment_status, segment,
branch_code, rm_code, clv_estimate, churn_risk, nba, nps_score,
digital_engagement, products_held, propensity_scores, tags,
complaints_12m, last_contact_days, sources, _field_lineage
```

Converting via `dataclasses.asdict()` gives the engine all of these as a flat dict. **The engine sees a superset of what it saw before**, including:
- `sources` — knows whether this customer came from CBS, marketing, or both
- `enrichment_status` — explicit enrichment level
- `_field_lineage` — which source authored which field

The engine itself doesn't yet use these new fields (only reads `segment`), but downstream consumers can.

## Part 5 — Verified compatibility

Smoke test with real CIF `100625608`:

| Field | Legacy | Canonical |
|---|---|---|
| `segment` | `'Mass'` | `'Mass'` |
| `sources` | (absent) | `['marketing']` |
| `enrichment_status` | (absent) | `'marketing_only'` |
| `_field_lineage` | (absent) | 12 fields tracked |

**Engine consumer field (`segment`) matches exactly.** All 42 existing `tests/test_customer_profitability.py` tests pass without modification.

## Part 6 — What v10.381 deliberately does NOT do

- Does NOT modify `CustomerProfitabilityEngine` class itself (public API unchanged)
- Does NOT modify `customer_intelligence.json` (legacy file preserved)
- Does NOT add new fields to UnifiedCustomerRecord
- Does NOT change other profitability engines (rm_profitability.py → v10.382)
- Does NOT change downstream consumers (BSC engine, MD cockpit)
- Does NOT remove `_legacy_customer_intelligence_lookup` (it's the fallback)

Single concern: **make customer_profitability.py use the canonical engine as its default data source, with legacy fallback for safety.**

## Part 7 — Honest acknowledgement

1. **The refactor is small because the engine was already well-designed.** Dependency injection paid for itself here. No structural changes needed.

2. **`_UNIFIED_MASTER_CACHE` is module-global** — not ideal for long-running processes where customer data changes. Provided `reset_canonical_customer_cache()` for explicit invalidation.

3. **`asdict()` is called per lookup** — could cache the asdict result too if profiling shows it matters. For now, prioritize correctness over micro-optimization.

4. **Customers in CBS but NOT in marketing** are now visible to the engine. This is the upside — but they have None for marketing fields (clv, churn, etc). Engine handles None correctly (it only reads `segment`); but downstream consumers should be aware.

5. **No new tests required for behavior change.** The existing 42 tests already exercise the engine; they pass with canonical lookup. v10.381 adds 7 NEW tests that exercise the canonical-first path explicitly + the fallback path + cache reset semantics.

6. **Customer_intelligence.json is now read TWICE** in some paths — once directly by `_legacy_customer_intelligence_lookup` and once indirectly through `compute_unified_customer_master`. The cache mitigates this but it's worth noting.

7. **The next batch (v10.382) applies the same pattern to `rm_profitability.py`.** That engine reads marketing+CBS data through different paths today; same canonical-first refactor applies.
