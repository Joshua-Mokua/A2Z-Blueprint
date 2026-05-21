# RM Profitability → Canonical Engine Refactor

**Version anchor:** v10.383 (May 2026)
**Per:** Phase B roadmap commitment from v10.381 / v10.382 wrap-ups
**Companion to:** `CUSTOMER_PROFITABILITY_CANONICAL_REFACTOR_v10.381.md`

> "Continue with v10.383 (rm_profitability canonical refactor)"

v10.381 brought `customer_profitability.py` onto the v10.378 canonical engine. v10.383 does the same for `rm_profitability.py` — same surgical pattern, same dependency-injection mechanics. The parallel profitability engines (customer + RM) are now both unified through v10.378.

---

## Part 1 — Why this matters (and the silent failure exposed)

### 1.1 Before v10.383

```
rm_profitability.py
    │
    ▼ (reads directly)
data/customer_intelligence.json   (3,000 marketing records, NO rm_code field)
```

The engine's `_default_rm_customer_lookup(rm_code)` iterated marketing records looking for `info.get("rm_code") == rm_code`. **Marketing intel records have no rm_code field.** Result: function always returned **empty list** — silently.

This is a **constitutional §5.4 violation already in production** — the engine was failing silently for every RM lookup. Every RM dashboard showed "0 customers" because the data path was wrong.

### 1.2 After v10.383

```
rm_profitability.py
    │
    ▼ (canonical-first via v10.378; legacy fallback)
utils.customer_master_canonical.compute_unified_customer_master()
    │
    ├── CBS customers (HAS rm_code from KYC)         ← previously invisible
    └── Marketing intel (no rm_code; fallback path)
```

The canonical engine merges CBS (where rm_code lives) with marketing intel (where analytics live). For RM-lookup queries, the CBS-authoritative rm_code drives the result.

### 1.3 Live evidence from refactor smoke test

```
Seed bank with CBS data:
  Unified master:     3,306 customers, 100 with rm_code
  Sample RM 300046:   4 customers under their portfolio

Engine result before vs after v10.383:
  Legacy (marketing only):  0 customers   ← silent zero
  Canonical (v10.378 path): 4 customers   ← real portfolio
```

**The refactor fixes a pre-existing bug, not just adds a feature.**

---

## Part 2 — Why the refactor stayed surgical

Same architectural advantage as v10.381: the engine already had dependency injection. `RMProfitabilityDashboard` accepts `rm_customer_lookup_fn`. Default was `_default_rm_customer_lookup` reading marketing intel directly.

v10.383 replaces only the **internal default**:
- `_default_rm_customer_lookup` keeps the same name
- Its implementation now calls `_canonical_rm_customer_lookup_v10383` first
- Falls back to `_legacy_rm_customer_lookup` if canonical engine unavailable

Public API unchanged. Callers passing their own `rm_customer_lookup_fn` are unaffected.

---

## Part 3 — Module changes

| Symbol | Before | After |
|---|---|---|
| `_default_rm_customer_lookup` | Read marketing intel directly | Canonical-first dispatcher |
| `_canonical_rm_customer_lookup_v10383` | — | NEW — calls v10.378, builds rm_code → cifs index |
| `_legacy_rm_customer_lookup` | — | RENAMED from old `_default_rm_customer_lookup` body |
| `reset_canonical_rm_cache` | — | NEW — test helper |
| `_RM_UNIFIED_MASTER_CACHE` | — | Module-level cache (unified master per process) |
| `_RM_BY_RM_CODE_INDEX` | — | Module-level cache (rm_code → cifs index) |

The two caches are populated lazily on first lookup. `reset_canonical_rm_cache()` clears both.

---

## Part 4 — Why two caches instead of one

The unified master has 3,306 records (seed bank) and would have 700k+ in production. Iterating it on every RM lookup is O(N). The `_RM_BY_RM_CODE_INDEX` provides O(1) lookup per RM.

Trade-off: more memory (a Dict[str, List[str]]) but O(1) lookups. Reasonable for a process serving many RM queries.

---

## Part 5 — Verified compatibility

| Check | Status |
|---|---|
| Existing 34 `tests/test_rm_profitability.py` tests | **all pass** unchanged |
| `_default_rm_customer_lookup` public signature preserved | YES |
| Returns List[str] of CIFs (unchanged contract) | YES |
| Empty list for unknown RM | YES |
| Module-level cache resets correctly | YES |

The behavioral change is **net-positive**: previously silent zeros become real customer lists when CBS data is wired through.

---

## Part 6 — What v10.383 deliberately does NOT do

- Does NOT modify `RMProfitabilityDashboard` class itself (public API unchanged)
- Does NOT modify `customer_intelligence.json` (legacy data preserved)
- Does NOT change `_default_rm_lookup` (RM identity lookup — reads users.json, not customer data; correct as-is)
- Does NOT change `_default_all_rms` (RM enumeration — also reads users.json; correct)
- Does NOT change `_default_customer_pnl` (delegates to customer_profitability engine — already canonical post-v10.381)
- Does NOT auto-load CBS data at import time
- Does NOT touch the RM Performance pages (they call this engine via existing public API)

Single concern: **make rm_profitability.py consume v10.378 canonical master for its customer-portfolio lookup, with legacy fallback.**

---

## Part 7 — Honest acknowledgements

1. **The "silent zero" bug existed before v10.383.** Anyone running RM profitability dashboards on the production system was seeing empty portfolios because marketing intel has no rm_code field. The deep review caught this only because we surveyed the data flow.

2. **The fix is automatic once CBS data is on disk.** No config change needed. As soon as `cbs_data/` is populated, RM dashboards will populate. This is a quiet, structural improvement.

3. **The legacy fallback returns empty for the seed bank** (marketing intel has no rm_codes). This is consistent with pre-v10.383 behavior — the fallback preserves the old (broken) behavior so callers that rely on emptiness don't break unexpectedly.

4. **Two caches (master + index) are populated together.** They're consistent by construction; if one is stale the other is too. Both clear on `reset_canonical_rm_cache()`.

5. **The customer-profitability cache (v10.381 `_UNIFIED_MASTER_CACHE`) is SEPARATE** from this module's `_RM_UNIFIED_MASTER_CACHE`. Two process-wide caches of the same data. Acceptable for now (each module independent). Worth consolidating if memory becomes an issue.

6. **No new RM identified by this refactor.** RMs still come from users.json (`_default_all_rms` unchanged). v10.383 just makes the customers-per-RM lookup correct.

7. **Phase B parallel-engines arc COMPLETE.** Customer + RM profitability both consume v10.378 canonical master after v10.383. The body's circulatory organ (profitability) is fully wired through the recognition organ (customer master).
