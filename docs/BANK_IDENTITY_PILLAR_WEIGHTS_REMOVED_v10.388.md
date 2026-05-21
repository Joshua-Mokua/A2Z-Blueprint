# Bank Identity Pillar Weights — Dead Branch Removed

**Version anchor:** v10.388 (May 2026)
**Per:** v10.385 Deep Body Diagnosis — Tier-1 fix sequence (Finding P3 — prioritization organ consolidation)
**Phase:** Phase C (continues v10.386's working-tab migration)

The deprecation period ended. The dead form is amputated.

---

## Part 1 — The commitment we kept

v10.384 added this deprecation notice to the Bank Identity admin tab (visible in the UI):

> ⚠️ **Deprecated.** Changes to pillar weights HERE do NOT affect BSC scoring. They write to a legacy location no longer read by the scoring engine. **To change pillar weights, go to: Admin → KPI Library → Pillar weights tab.** That tab writes to the canonical store (`kpi_library.json::pillar_weights`) with audit-history. This section is preserved only for backward compatibility and **will be removed in v10.388**.

v10.388 keeps that commitment.

The promise was captured in code (not just in a roadmap doc) — operators saw it in the UI. The audit gate G270 verified the deprecation marker referenced v10.388 specifically. The body's commitment-to-self was tracked. v10.388 fulfills it.

---

## Part 2 — What was removed

### 2.1 The form widgets (4 number inputs + total display)

```python
# REMOVED in v10.388:
_pw1,_pw2,_pw3,_pw4 = st.columns(4)
_pillar_wts = _org.get("pillar_weights",{})
_fin_wt  = _pw1.number_input("Financial %",  0, 100, _pct("Financial", 40))
_cust_wt = _pw2.number_input("Customer %",   0, 100, _pct("Customer Focus", 25))
_ops_wt  = _pw3.number_input("Operations %", 0, 100, _pct("Operational Excellence", 25))
_ppl_wt  = _pw4.number_input("People %",     0, 100, _pct("People & Learning", 10))
_wt_total = _fin_wt+_cust_wt+_ops_wt+_ppl_wt
# ... colored validation display
```

These had no effect on scoring since they wrote to `org_config.json::pillar_weights` (orphan location, no consumers).

### 2.2 The sum-validation gate on the form submit

```python
# REMOVED in v10.388:
if st.form_submit_button("💾 Save bank identity", type="primary"):
    if _wt_total != 100:
        st.error("Pillar weights must total 100%")
    else:
        # ... rest of save
```

The form-submit no longer rejects on pillar weight sum. Since pillar weights aren't being collected by this form anymore, the validation is moot.

### 2.3 The dead-branch write

```python
# REMOVED in v10.388:
_org["pillar_weights"] = {
    "Financial": _fin_wt/100, "Customer Focus": _cust_wt/100,
    "Operational Excellence": _ops_wt/100, "People & Learning": _ppl_wt/100}
```

This was the line that silently went nowhere. v10.388 deletes it.

### 2.4 The deprecation warning

The big yellow `st.warning(...)` block from v10.384 is replaced by a brief `st.info(...)` redirect explaining where pillar weights live now.

---

## Part 3 — What replaces it

A small `st.info` notice (no widgets, no save logic):

```python
st.info(
    "ℹ️ **Pillar weights moved.** Pillar weights are managed at "
    "**Admin → KPI Library → Pillar weights tab**. That tab "
    "writes to the canonical store with audit history. The form "
    "that lived here previously wrote to a legacy location no "
    "longer read by scoring — it has been removed in v10.388."
)
```

This serves two purposes:
1. **Operator wayfinding** — anyone who remembered seeing pillar weights here now knows where they went
2. **Historical traceability** — the redirect references v10.388, anchoring the removal in version history

---

## Part 4 — What was preserved

| Item | Why preserved |
|---|---|
| Bank Identity tab itself | Tab still serves identity-only fields (bank_name, bank_code, country, currency, regulator, etc.) |
| Bank Identity form's `st.form_submit_button` save | All non-pillar identity fields still need their save logic |
| `org_config.json::pillar_weights` data on disk | Orphan removal scheduled for v10.390 with broader cleanup (keep the data intact while form is being removed; don't bundle data cleanup) |
| KPI Library → Pillar weights tab (canonical) | The working tab is unchanged; v10.386 migrated it, v10.388 doesn't touch it |
| `pillars[].weight` shadow data | Scheduled for v10.389 removal — that's a separate concern |

---

## Part 5 — What v10.388 deliberately does NOT do

Per Rule N2 (single concern):

- Does **NOT** remove `org_config.json::pillar_weights` data field (v10.390)
- Does **NOT** remove `pillars[].weight` shadow data in kpi_library.json (v10.389)
- Does **NOT** touch the KPI Library → Pillar weights working tab
- Does **NOT** change canonical pillar weight values
- Does **NOT** modify the `save_org_config` function (still saves the dict including any preserved pillar_weights field)
- Does **NOT** modify `pillar_weights_canonical.py`

Single concern: **remove the dead UI form and its dead-branch write from `pages/7_admin.py`.**

---

## Part 6 — Body-system framing

The body's prioritization organ had a phantom limb — a UI control that operators could touch but that didn't connect to anything. The deprecation period was its rehabilitation: operators were warned, those who paid attention migrated to the working tab.

v10.388 is the surgical amputation. Phantom limb gone. The body has one pillar-weights pathway (canonical), and it works.

This is **post-rescue care** for the prioritization organ. v10.384 stopped the bleeding (made the silent failure visible). v10.386 wired the working pathway through canonical lungs. v10.388 removes the dead tissue.

Per constitution §12 (Flow Principle): the body should have one source of truth per concern. After v10.388, there's no UI confusion about which "pillar weights" tab is correct — there's only one place that takes input. The body knows itself.

---

## Part 7 — Verification + remaining work

### 7.1 Verified by G273

- Old form widgets removed (`_pw1`, `_fin_wt`, `_cust_wt`, `_ops_wt`, `_ppl_wt`, `_pillar_wts = _org`)
- Old dead-branch write removed (`_org["pillar_weights"] = ...`)
- Redirect info notice present with v10.388 marker
- Admin page parses cleanly (AST)
- KPI Library Pillar Weights tab unchanged (canonical accessor imports + save_pillar_weights call still present per v10.386 contract)

### 7.2 Remaining Tier-1 work after v10.388

| Batch | Concern |
|---|---|
| v10.389 | Remove `pillars[].weight` shadow data from `kpi_library.json` |
| v10.390 | Remove `org_config.json::pillar_weights` orphan field + start Tier-1 Class B KPIs |
| v10.391 | Tier-2 Class B KPIs |

After v10.390, the prioritization organ rescue is **fully complete**: one canonical store, one admin UI, no shadow data, no orphan locations, full audit history. The body has truly singular pillar weights.

---

## Part 8 — Honest acknowledgements

1. **This was the easiest batch of Phase C so far.** ~30 LOC removed from `pages/7_admin.py`. The hardest part was being careful about indentation (3 lines moved from inside an `else` branch to top-level of the form submit).

2. **The deprecation period was about 4 batches** (v10.384 → v10.388). Long enough for operators to notice the warning, short enough that the dead branch didn't linger indefinitely.

3. **`org_config.json::pillar_weights` data is preserved on disk.** v10.388 stops writing to it but doesn't delete the existing data. v10.390 removes the field entirely. Two-stage removal is safer (allows rollback if something unexpected breaks).

4. **The Bank Identity tab still saves successfully.** Pre-v10.388, the save included pillar_weights and required sum=100. Post-v10.388, the save just persists identity fields. Faster and cleaner. Operators saving bank metadata no longer have to also satisfy a pillar weights constraint that did nothing.

5. **No operator data lost.** Canonical weights remain at 68/14/6/12 (or whatever current value). KPI Library tab continues to work. History continues to populate.

6. **The redirect notice is brief.** No yellow warning, no scary tone. Just an informational pointer. The crisis is over; this is just a redirect.

7. **G273 uses targeted assertion.** Checks that specific symbols (`_pw1`, `_fin_wt`, etc.) are absent from the Bank Identity section but doesn't claim they're absent from the whole file (the KPI Library section uses `_new_pw` etc. — different names anyway, but worth being explicit).

8. **The `if _wt_total != 100` validation was redundant** even pre-v10.388 because the dead branch made the validation moot. Removing it didn't change observable behavior.

9. **Rule N2 single concern held strictly.** Removed ONE UI section + ONE field write. Did NOT touch the data file, the canonical accessor, the working tab, or any other organ.

10. **The body is becoming more singular.** Each removal of dead tissue brings the body closer to what the constitution §12 envisions: one source of truth per concern, no silent failures, no orphan UIs. v10.388 is one step on that path.
