# Pillar Weights Admin Module — Deep Review

**Version anchor:** v10.382 (May 2026)
**Per:** Joshua's directive — *"we had a recommendation to have them configured at the admin module so you may want to do a deep review on the same as well"*

You had a previous recommendation that pillar weights should be admin-configurable (not hard-coded). The current state is **mostly there but with critical drift**. This document surveys what's deployed today and what needs to change.

---

## Part 1 — Current state inventory

### 1.1 Three storage locations (architectural drift)

| # | Location | Format | Default | Status |
|---|---|---|---|---|
| 1 | `kpi_library.json::pillar_weights` (dict) | `{"Financial": 0.40, ...}` | 40/25/25/10 baseline, currently **68/14/6/12** | **CANONICAL** (most consumers read this) |
| 2 | `kpi_library.json::pillars[]` (array, each with .weight) | `[{"name": "Financial", "weight": 0.40}, ...]` | 40/25/25/10 | OLD format — read in some places, written nowhere |
| 3 | `org_config.json::pillar_weights` (dict) | `{"Financial": 0.40, ...}` | 40/25/25/10 | **ORPHAN — written by admin Bank Identity tab, NOT read anywhere** |

### 1.2 Two admin UIs that edit "pillar weights"

| Admin UI location | What it claims to do | Where it writes | What actually reads it |
|---|---|---|---|
| Tab "Bank Identity" (line 145-180 of `pages/7_admin.py`) | "Pillar weights — how the BSC score is computed bank-wide" | `org_config.json::pillar_weights` | **NOTHING** ❌ |
| Tab "KPI Library" → "Pillar weights" sub-view (line 2116+ of `pages/7_admin.py`) | "Set the weight of each pillar in the overall BSC score" | `kpi_library.json::pillar_weights` | Everything that matters ✓ |

### 1.3 Consumers of `kpi_library.json::pillar_weights`

Verified by grep:
- `utils/actuals_engine.py` line 261 — uses for actuals scoring
- `utils/core.py` line 1478 — `get_pillar_weights()` helper
- `pages/1_perform.py` line 478 — BSC scorecard rendering
- `pages/12_cascade.py` line 803 — cascade weighted view
- `pages/7_admin.py` line 2048 — KPI Library Pillar Weights tab

5 readers, all from `kpi_library.json`. None from `org_config.json`.

### 1.4 Consumers of `kpi_library.json::pillars[]`

- `utils/actuals_engine.py` line 136 — iterates `pillars` to find KPIs per pillar
- `utils/actuals_engine.py` line 270 — reads pillars_data
- `utils/core.py` line 1467 — iterates pillars for KPI assignment
- `pages/1_perform.py` line 486 — renders BSC by pillar
- `pages/12_cascade.py` line 802 — cascade by pillar
- `pages/7_admin.py` line 2038 — activate-KPIs tab

`pillars[]` is read for **structure** (which KPIs belong to which pillar) but the WEIGHT in each pillar entry is NOT actively used — `pillar_weights` dict overrides.

---

## Part 2 — The defects

### Defect 1 — Two admin UIs edit the same concept, only ONE works

A user opening "Bank Identity" tab sees pillar weight sliders, adjusts them, saves. **Nothing changes in BSC scoring.** The user thinks they've changed the weights; they haven't.

This is a **silent failure** — exactly the kind constitution §5.4 forbids.

**Severity:** HIGH — user confusion, false sense of control, audit-trail confusion.

### Defect 2 — Defaults drift between admin UIs

Both UIs use 40/25/25/10 as the "default" when no value present. But the current `kpi_library.pillar_weights` is **68/14/6/12** (per v10.380 deep review). So:
- Bank Identity tab shows the user 40/25/25/10 (its hardcoded default)
- KPI Library → Pillar weights tab shows the user 68/14/6/12 (the actual stored value)
- Two different "current weights" depending on which tab you visit

**Severity:** HIGH — operator confusion, no single source of truth visible.

### Defect 3 — `pillars[].weight` is shadow data

The `pillars[]` array has weights (40/25/25/10) per pillar, but nothing reads them — `pillar_weights` dict overrides. So `pillars[].weight` is dead data that historians might think is the source of truth.

**Severity:** MEDIUM — clutter, no live impact, but documentation drift.

### Defect 4 — Default fallback masks the real config

Each consumer does:
```python
_pillar_weights = _lib.get("pillar_weights", {
    "Financial": 0.40, "Customer Focus": 0.25,
    "Operational Excellence": 0.25, "People & Learning": 0.10
})
```

If `pillar_weights` is missing OR corrupted (wrong type, malformed dict), consumer **silently uses the hardcoded default**. No warning to admin. Falls back to 40/25/25/10 even though stored value may be different.

**Severity:** MEDIUM — debuggability issue; matches Defect 2 concern.

### Defect 5 — No history / audit trail

Admin changes pillar weights, the library is overwritten. No record of:
- Previous weights
- When they changed
- Who changed them
- Why

The `audit_log` function is called for `BANK_IDENTITY_SAVED` but the actual weight values aren't captured in the log message.

**Severity:** MEDIUM — audit gap (§8.1).

### Defect 6 — Per-role pillar weights have a separate (older) structure

`ROLE_MAP` in an older module assigned per-role weights (Procurement Manager 0.25/0.25/0.50, etc.). Per-role weights are NOT in `pillar_weights` dict — they're elsewhere. So bank-wide vs per-role weights are TWO separate stores.

**Severity:** LOW (today most roles inherit bank-wide weights) but **HIGH** if Joshua wants role-specific pillar weights to matter.

---

## Part 3 — Recommended consolidation

### 3.1 Choose ONE canonical location

**Recommendation:** `kpi_library.json::pillar_weights` is canonical (already 5 readers). 

Action:
1. Remove the Bank Identity tab's pillar weight section (Defect 1 fixed)
2. Direct users to KPI Library → Pillar weights tab (the working one)
3. Remove `org_config.json::pillar_weights` (orphan)
4. Update `pillars[]` to derive weights from `pillar_weights` dict at read time OR drop `weight` from `pillars[]` entirely

### 3.2 Strengthen the admin UI

The working Pillar weights tab should:
- Display CURRENT weights (read from library) instead of generic defaults
- Validate: sum must equal 100% (already enforced)
- Validate: each weight must be > 0 (no killing a pillar)
- Optional: enforce minimum/maximum range per pillar (e.g. Financial 30%-60%)
- Show preview: "If you save this, your MD's BSC will recompute as follows..."
- Save with audit-log message capturing the OLD and NEW values

### 3.3 Add version history

Save weight changes to `kpi_library_pillar_weights_history.json`:
```json
[
  {
    "changed_at": "2026-04-15T10:00:00",
    "changed_by": "olive001",
    "old_weights": {"Financial": 0.40, ...},
    "new_weights": {"Financial": 0.68, ...},
    "reason": "Crisis quarter focus on financial recovery"
  }
]
```

Admin UI shows last 10 changes; recent rebalancing context preserved.

### 3.4 Bank Identity tab refocus

Bank Identity tab should retain identity-only fields (bank_name, bank_code, country, currency) and DROP the pillar weights section. Add a notice: "Pillar weights → KPI Library tab → Pillar weights sub-view."

### 3.5 Per-role pillar weights — defer with documentation

The recommendation: **Don't yet implement per-role pillar weights.** The current model is one set of weights for all staff, which:
- Matches Kaplan & Norton's original BSC framing (one balanced score per role hierarchy)
- Is what 5/5 current consumers expect
- Is what target_cascade can already cascade (one weight set)

If per-role weights become important later (e.g. a Treasury role needs different Financial weight than Marketing), it can be added as `role_pillar_weight_overrides` field — a sparse exception layer on top of bank-wide weights.

### 3.6 Threshold integration

Per constitution §11.1 + the spec excerpt about Tab 23 (Thresholds — 60 configurable items), pillar weights ideally live there as **bank-wide thresholds**. The proposal:

- Admin Tab 23 (Thresholds) gets a **"Pillar Weights"** section alongside CIR target, NPS thresholds, etc.
- Consumes the same canonical `kpi_library.json::pillar_weights`
- Removes redundancy between Tab 23 and KPI Library → Pillar weights sub-view

This consolidates "weights" with other "configurable scoring parameters."

---

## Part 4 — Implementation steps (suggested batch sequence)

| Step | Batch | Action | Risk |
|---|---|---|---|
| A | v10.384 (with KPI Tier 1) | Add `pillar_weights_history.json` schema | Low |
| B | v10.385 | Refactor Bank Identity tab — drop pillar weights, redirect users | Medium (UX change) |
| C | v10.386 | Strengthen KPI Library Pillar weights tab — show OLD/NEW, audit-log, history | Medium |
| D | v10.387 | Remove `org_config.json::pillar_weights` orphan field | Low (no readers exist) |
| E | v10.388 | Remove `pillars[].weight` shadow data (keep `pillars[]` structure for KPI grouping) | Low |
| F | v10.389+ | (Optional) Move to Tab 23 alongside other thresholds | Medium |

---

## Part 5 — On the 40/25/25/10 vs 68/14/6/12 debate

The current stored value is **68/14/6/12** (Financial-dominant). My v10.381 recommendation was to return to **40/25/25/10** (balanced).

This deep review of the admin module surfaces an extra consideration: **whoever set 68/14/6/12 today may not realize their change to Bank Identity tab does NOTHING.** They likely changed it through KPI Library → Pillar weights tab (the working UI). That tells us:

- Someone deliberately chose to weight Financial at 68%
- This was a real decision, not an accident
- Returning to 40/25/25/10 should be an equally deliberate decision

**Recommendation:** Before changing weights back, audit-log who made the 68/14/6/12 change and when. If it was a crisis-quarter decision (Decision 2 in v10.381 doc), document the return-to-balance date.

---

## Part 6 — Body-system framing

Pillar weights are the **body's prioritization organ** — what matters how much. When the body has TWO competing prioritization organs (the working KPI-Library one + the dead Bank-Identity one), the body becomes confused about its own values. Some organs read from one set of priorities; others read from the other; the result is uncoordinated effort.

This is exactly the failure mode constitution §12 (Flow Principle) warns about — the body's various organs need to share a consistent set of priorities or the body works against itself.

After consolidation:
- ONE prioritization organ (canonical kpi_library.pillar_weights)
- All other organs (BSC engine, perform page, cascade page, MD cockpit) read from the same organ
- Audit trail of every change to priorities
- Clear validation rules so priorities can't be set illegibly

The body knows its own priorities — every organ acts in alignment.

---

## Part 7 — What v10.382 deliberately does NOT do

This review document does not ship code changes. v10.382 explicitly:

- Does NOT modify `pages/7_admin.py`
- Does NOT modify `kpi_library.json`
- Does NOT modify `org_config.json`
- Does NOT remove the orphan Bank Identity pillar weights section
- Does NOT change pillar weights from 68/14/6/12 to 40/25/25/10

Implementation is queued for v10.384+ pending Joshua's approval.

---

## Part 8 — Joshua decisions queued from this review

| # | Question |
|---|---|
| W1 | Confirm `kpi_library.json::pillar_weights` is canonical (remove other locations)? |
| W2 | Approve removing the Bank Identity tab pillar-weights section (Defect 1 fix)? |
| W3 | Add version history (`pillar_weights_history.json`)? |
| W4 | Should pillar weights eventually move to Tab 23 (Thresholds), or stay in KPI Library tab? |
| W5 | Approve return to 40/25/25/10, OR document 68/14/6/12 as deliberate with return date? |
| W6 | Per-role pillar weights — defer as recommended, or address now? |
| W7 | Add validation rules (min weight per pillar, e.g. no pillar < 5%)? |
| W8 | Audit-log every weight change with OLD/NEW values? |
