# KPI Library Pillar Weights — Canonical Save Migration

**Version anchor:** v10.386 (May 2026)
**Per:** Phase C Tier-1 fix sequence from v10.385 body diagnosis
**Pre-requisite:** v10.384 canonical accessor (`utils/pillar_weights_canonical.py`)

The KPI Library → Pillar Weights admin tab is the **working** UI for changing pillar weights (the canonical path). Before v10.386 it wrote directly to `kpi_library.json` with only sum=100 validation and no audit trail. v10.386 migrates it to use the canonical `save_pillar_weights()` accessor — gaining validation + history + audit-log.

This is the first Phase C execution batch against the v10.385 diagnosis.

---

## Part 1 — What changed

### Before v10.386

```python
if st.form_submit_button("💾 Save weights", type="primary"):
    if _pw_total == 100:
        _lib["pillar_weights"] = _new_pw
        save_kpi_library(_lib)
        st.success("✅ Pillar weights saved.")
        st.rerun()
    else:
        st.error("Pillar weights must total 100%.")
```

**What this lacked:**
- No validation that all 4 canonical pillars present
- No validation that all weights > 0 (a zero pillar = dead organ)
- No history capture — change happens, no record kept
- No audit-log of OLD vs NEW values
- Reads `_pillar_weights` from page-scoped variable that may be stale

### After v10.386

```python
from utils.pillar_weights_canonical import (
    get_pillar_weights, save_pillar_weights,
    get_pillar_weights_history, CANONICAL_PILLARS,
)

# Read FRESH canonical state
_pw_current = get_pillar_weights()

# ... form input ...

if st.form_submit_button("💾 Save weights", type="primary"):
    _ok, _msg = save_pillar_weights(
        _new_pw, actor=uname, reason=_pw_reason,
    )
    if _ok:
        st.success("✅ Pillar weights saved to canonical store. Change captured in audit history.")
        audit_log("PILLAR_WEIGHTS_SAVED", uname, f"new={_new_pw} reason={_pw_reason!r}")
        st.cache_data.clear()
        st.rerun()
    else:
        st.error(f"❌ Save rejected: {_msg}")

# Recent history shown beneath form
_hist = get_pillar_weights_history(limit=5)
# ... renders OLD vs NEW per change ...
```

**What this adds:**
- Full validation per `pillar_weights_canonical.validate_pillar_weights`:
  - All 4 canonical pillars required
  - Each weight > 0 (no dead organs per §12 Flow Principle)
  - Sum = 1.0 ± 0.001
- Every save appends to `pillar_weights_history.json` with OLD/NEW
- Optional **reason** text input captured in audit trail
- Recent history (last 5 changes) shown beneath the form
- Reads fresh canonical state (not page-scoped stale copy)
- Better error message when save rejected

---

## Part 2 — UI additions

### 2.1 Reason input

A new text input appears in the form:
> **Reason for change** (optional, captured in audit history)
> *placeholder: "e.g. Return to balanced posture after crisis quarter"*

Operators can document why they're changing weights. This is captured in the history entry alongside OLD/NEW values.

### 2.2 Recent history view

Beneath the form, last 5 history entries shown as expanders:
> 📜 Recent history (last 5 changes)
>
> [2026-05-15T10:00:00 — olive001 — Return to balanced...] (expandable)
>   - Old:  Financial 68%, Customer Focus 14%, Op Excellence 6%, People 12%
>   - New:  Financial 40%, Customer Focus 25%, Op Excellence 25%, People 10%

Auditors can see who changed what, when, and why — directly in the admin UI.

### 2.3 Better save messaging

| Scenario | Old message | New message |
|---|---|---|
| Save OK | "Pillar weights saved." | "Pillar weights saved to canonical store. Change captured in audit history." |
| Sum != 100 | "Pillar weights must total 100%." | "Save rejected: validation failed: weights sum to 0.95, must be 1.0 ± 0.001" |
| Zero pillar | (silently allowed) | "Save rejected: validation failed: pillar 'Financial' weight must be > 0 ... a pillar with zero weight is a dead organ" |
| Missing pillar | (silently allowed) | "Save rejected: validation failed: missing pillars: ['People & Learning']" |

---

## Part 3 — What v10.386 deliberately does NOT do

Per Rule N2 (single concern), v10.386 explicitly:

- Does NOT change canonical pillar weights value (still 68/14/6/12 or whatever it currently is)
- Does NOT remove the deprecated Bank Identity tab section (that's v10.388)
- Does NOT remove `pillars[].weight` shadow data (that's v10.389)
- Does NOT delete `org_config.json::pillar_weights` orphan (that's v10.390)
- Does NOT migrate the cascade page's separate pillar_weights read path (separate concern; the cascade page reads canonical location which is fine)
- Does NOT add per-role pillar weights (Decision W6 still pending)

Single concern: **migrate the KPI Library Pillar Weights admin tab to the canonical save accessor.**

---

## Part 4 — Verification

| Check | Status |
|---|---|
| pages/7_admin.py parses cleanly | ✓ |
| Tab imports `save_pillar_weights` from canonical | ✓ |
| Save button calls `save_pillar_weights(_new_pw, actor, reason)` | ✓ |
| Error path renders rejection message | ✓ |
| Reason text input present | ✓ |
| History view renders below form | ✓ |
| Uses CANONICAL_PILLARS constant (not page-scoped dict) | ✓ |
| Calls audit_log on successful save | ✓ |
| Existing v10.384 canonical module unchanged | ✓ |

---

## Part 5 — How this advances the prioritization-organ rescue

| Batch | Concern | Status |
|---|---|---|
| v10.384 | Canonical accessor + history schema + admin deprecation notice | ✅ shipped |
| **v10.386** | **Migrate KPI Library tab to canonical save** | **✅ this batch** |
| v10.387 | Add History view to admin tab (already done as part of v10.386!) | rescheduled |
| v10.388 | Remove deprecated Bank Identity pillar weights form | upcoming |
| v10.389 | Remove `pillars[].weight` shadow data | upcoming |
| v10.390 | Remove `org_config.json::pillar_weights` orphan | upcoming |

v10.386 actually bundles v10.387 (History view) since the canonical accessor already provides `get_pillar_weights_history` and rendering it is trivial. Saves a batch in the sequence.

---

## Part 6 — Body-system framing

The prioritization organ now has:
1. **One canonical voice** (kpi_library.json::pillar_weights — unchanged from v10.384)
2. **One canonical accessor** (`utils.pillar_weights_canonical` — unchanged from v10.384)
3. **One working admin UI calling the accessor** (this batch — KPI Library Pillar Weights tab now flows through validation + history)
4. **Audit trail captured at every save** (history file + audit_log)
5. **The silent voice still exists but is loudly deprecated** (Bank Identity tab; removal v10.388)

The body's prioritization organ is **acting healthily** for every change made through the canonical UI. The remaining work is removing the dead branches (v10.388-v10.390).

---

## Part 7 — Honest acknowledgements

1. **The History view was originally scheduled for v10.387.** It's so cheap to add (the accessor already exposes `get_pillar_weights_history`) that bundling into v10.386 saves a batch. Documented in roadmap.

2. **The change is mechanically small.** ~80 lines of replaced admin tab code. No new modules. No new gates needed beyond G272. But the behavior change is substantive: validation + history + audit.

3. **Operators using the OLD form behavior may be surprised** by stricter validation. Pre-v10.386 a "Pillar weights must total 100%" error was the only path. Post-v10.386 they may hit "weights sum to 0.999..." (float arithmetic — but tolerance is 0.001) or "Financial weight must be > 0" — both useful messages.

4. **The page-scoped `_pillar_weights` variable still exists** in surrounding code (used by Role Assignments tab to display pillar headers). v10.386 doesn't refactor those — they read library state for display purposes only. Separate concern.

5. **The audit_log call is preserved alongside the new history file.** Two audit mechanisms (the in-app audit_log + the canonical history file) capture the same event. Acceptable redundancy for now; consolidation possible later but not urgent.

6. **The reason text input is optional.** No enforcement. Operators can save without giving a reason. The audit history still captures who and when.

7. **The History view caps at 5 entries** to keep the UI tidy. The underlying file holds 100 (per v10.384 module config). Full history accessible via direct file read if needed.

8. **First Phase C execution batch shipped.** The diagnosis (v10.385) becomes action. Body repair begins.
