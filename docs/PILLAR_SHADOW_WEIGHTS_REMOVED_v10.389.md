# Pillar Shadow Weights — Removed from kpi_library.json::pillars[]

**Version anchor:** v10.389 (May 2026)
**Per:** v10.385 Deep Body Diagnosis — Tier-1 fix sequence (Finding P3 — prioritization organ consolidation)
**Phase:** Phase C continues (continues v10.386 + v10.388 prioritization rescue)

The shadow data is removed. `pillars[]` now carries only structural metadata; weights live in `pillar_weights` dict.

---

## Part 1 — What was the shadow?

Inside `data/kpi_library.json`:

```json
"pillars": [
  {"id": "Financial",              "name": "Financial Performance",   "weight": 0.4,  "color": "#0F6E56"},
  {"id": "Customer Focus",         "name": "Customer Focus",          "weight": 0.25, "color": "#185FA5"},
  {"id": "Operational Excellence", "name": "Operational Excellence",  "weight": 0.25, "color": "#854F0B"},
  {"id": "People & Learning",      "name": "People & Learning",       "weight": 0.1,  "color": "#3C3489"}
]
```

The `weight` field in each entry: **40 / 25 / 25 / 10** (Kaplan-Norton balanced).

Meanwhile, `kpi_library.json::pillar_weights` (the canonical dict):

```json
"pillar_weights": {
  "Financial":              0.68,
  "Customer Focus":         0.14,
  "Operational Excellence": 0.06,
  "People & Learning":      0.12
}
```

Different values. **Two parallel "pillar weights" in the same file.**

The dict is canonical (5 consumers read from it including BSC scoring engine). The array's `weight` fields were vestigial — read for pillar structure (id, name, color) but the `weight` value was ignored because `pillar_weights` overrides.

---

## Part 2 — Why this was a problem

| Symptom | Severity |
|---|---|
| Two values for the same concept inside the same file | Confusion |
| Operator inspecting library file sees "40/25/25/10" in pillars[].weight, "68/14/6/12" in pillar_weights — doesn't know which is authoritative | Documentation drift |
| Future readers could misinterpret pillars[].weight as authoritative | Architectural risk |
| The two values diverged at some point — silent drift | §5.4 silent failure (mild form) |

This was Finding P3 in the v10.385 body diagnosis and Defect 3 (MEDIUM severity) in the v10.382 pillar weights admin review.

---

## Part 3 — What v10.389 changed

### 3.1 Data change (`data/kpi_library.json`)

For each of the 4 pillar entries in the `pillars[]` array, the `weight` field was removed. The other fields (`id`, `name`, `color`) are preserved — those drive pillar styling (color codes for BSC scorecard rendering) and KPI-pillar grouping (via `id`).

**Before:**
```json
{"id": "Financial", "name": "Financial Performance", "weight": 0.4, "color": "#0F6E56"}
```

**After:**
```json
{"id": "Financial", "name": "Financial Performance", "color": "#0F6E56"}
```

### 3.2 No code changes

The 5 canonical consumers continue reading from `pillar_weights` dict. They are unaffected.

The other consumers (those that iterate `pillars[]`) read `id`, `name`, `color` — never `weight`. They are unaffected.

### 3.3 Backup preserved

The pre-v10.389 file is preserved at `data/_v10389_backups/kpi_library.json.before`. Operational rollback is possible if anything unexpected breaks.

---

## Part 4 — Verified by health_check()

Pre-v10.389:
```python
>>> health_check()
{
  'canonical_weights': {Financial: 0.68, ...},
  'shadow_pillars_field': True,    # ← shadow data present
  'orphan_detected': {...},
  ...
}
```

Post-v10.389:
```python
>>> health_check()
{
  'canonical_weights': {Financial: 0.68, ...},
  'shadow_pillars_field': False,   # ← shadow removed ✓
  'orphan_detected': {...},        # still present, removed v10.390
  ...
}
```

The `health_check` function in `utils/pillar_weights_canonical.py` (v10.384) already had the diagnostic; v10.389 simply moves the boolean from True to False.

---

## Part 5 — Discovered along the way (separate finding, not bundled)

While verifying consumers, a **pre-existing bug** was discovered:

**`utils/core.py::get_active_kpis()`** does:
```python
for pillar, kpis in lib.get("pillars", DEFAULT_KPI_LIBRARY).items():
```

But `data/kpi_library.json::pillars` is a LIST of pillar metadata dicts, NOT a `dict[str, list]` (which is what `DEFAULT_KPI_LIBRARY` is, and what `.items()` requires).

**Live evidence:**
```python
>>> get_active_kpis()
AttributeError: 'list' object has no attribute 'items'
```

This is a separate bug from v10.389's concern. Per Rule N2 (single concern), v10.389 does NOT fix it. The bug is documented here for a future batch.

**Likely impact:**
- Any page calling `get_active_kpis()` crashes
- v10.385 body diagnosis didn't catch this (consumers were surveyed by grep, not by execution)
- May be why some older pages have pre-existing test failures

**New diagnostic finding (added to body diagnosis backlog):**

| Finding | Description | Severity | Suggested fix batch |
|---|---|---|---|
| **N7** | `get_active_kpis()` expects pillars as dict but data is list — AttributeError on call | MEDIUM | v10.392 or earlier |

This finding goes into the body's known-issues catalogue. v10.389 doesn't act on it.

---

## Part 6 — What v10.389 deliberately does NOT do

Per Rule N2 (single concern):

- Does NOT remove `org_config.json::pillar_weights` orphan (v10.390)
- Does NOT fix `get_active_kpis()` AttributeError (logged as Finding N7)
- Does NOT change the canonical pillar weight values
- Does NOT touch the canonical accessor module
- Does NOT touch any UI
- Does NOT remove the pillar entries themselves (the `id` / `name` / `color` structure is still needed)

Single concern: **delete the shadow `weight` field from each entry in `pillars[]`.**

---

## Part 7 — Body-system framing

The prioritization organ had a shadow whispering wrong numbers. Most consumers ignored the shadow (they listened to the canonical voice in `pillar_weights`). But the shadow was still there, in the same file, with different values, ready to confuse anyone reading the data.

v10.389 silences the shadow. The body's prioritization organ now speaks with ONE voice within `kpi_library.json`: the `pillar_weights` dict is authoritative; the `pillars[]` array holds only structural metadata.

The body sheds its dead weight.

Post-v10.389:
- `pillar_weights` (dict) — the voice that scoring engine hears
- `pillars[]` (list of structural metadata) — pillar names, ids, colors only
- No shadow data inside `kpi_library.json` for weights

The body is becoming truly singular per constitution §12 (Flow Principle). One canonical store per concern. v10.390 finishes the job by removing the `org_config.json::pillar_weights` orphan field too.

---

## Part 8 — Verified outcome

| Check | Status |
|---|---|
| `pillars[].weight` removed from all 4 entries | ✓ |
| `pillars[].id`, `name`, `color` preserved | ✓ |
| `pillar_weights` canonical dict unchanged (still 68/14/6/12) | ✓ |
| `health_check().shadow_pillars_field` flips to False | ✓ |
| Backup preserved at `data/_v10389_backups/kpi_library.json.before` | ✓ |
| No code changes (zero risk to consumer behavior) | ✓ |
| All 133 Phase B+C arc tests pass | ✓ |

---

## Part 9 — Honest acknowledgements

1. **Smallest batch of Phase C.** Four field deletions. Doc, gate, tests around the data change.

2. **Pre-existing bug discovered.** `get_active_kpis()` is broken — calls `.items()` on a list. v10.389 didn't introduce it, doesn't fix it, but logs Finding N7 for a future batch.

3. **The shadow had wrong values (40/25/25/10 baseline) vs canonical 68/14/6/12.** The drift had been silent. Anyone reading the JSON file directly would have seen two different "current weights" and not known which was authoritative.

4. **Backup pattern preserved.** `data/_v10389_backups/kpi_library.json.before` allows rollback. Same pattern as v10.345 and others.

5. **No code changes.** The 5 canonical consumers read from `pillar_weights` dict. The other consumers read `id`/`name`/`color` from `pillars[]`. Nobody read the shadow `weight` for scoring purposes. Safe to delete.

6. **The constitution §12 (Flow Principle) is the architectural anchor.** Body should have one source of truth per concern. Each batch in this rescue (v10.384, v10.386, v10.388, v10.389) gets closer to that ideal.

7. **Finding N7 is a real bug** but it's been there since `get_active_kpis()` was written. The discovery is the value; the fix is its own batch.

8. **Rule N2 single concern held strictly.** Even though discovering Finding N7 created an urge to fix it, the discipline held: log it, document it, but don't bundle.

9. **Health-check shape was already correct.** `utils/pillar_weights_canonical.py` (v10.384) had `shadow_pillars_field` in its health_check. We didn't add new diagnostic surface; we just made the existing one flip to False.

10. **Prioritization organ rescue 4-of-5 done.** v10.384 (canonical accessor) → v10.386 (working UI migration) → v10.388 (dead form removal) → **v10.389 (shadow data removal)**. Still pending: v10.390 (orphan field removal). After v10.390, the rescue is complete.
