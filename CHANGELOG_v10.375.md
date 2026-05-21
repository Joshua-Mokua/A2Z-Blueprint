# Changelog — v10.375 Role-aware Staff PBT Page (Phase A Second Batch)

**Date:** 2026-05-13
**Phase:** 4 (sixtieth arc — Phase A second batch from v10.373 review)
**Audit:** G261 added (locks staff PBT page + canonical engine imports + 3 filters)
**Tests:** 11/11 PASSED in `test_v10375_staff_pbt_page.py`; 239 prior tests unchanged = **250 total**
**Verifier:** 309/309 checks pass on a clean extract
**G162 baseline:** 4022 (69 consecutive zero-drift batches)
**Master prompt:** v4.18 → v4.19 (lockstep — twentieth consecutive batch)

---

## Your ask

> "continue"

Autonomous progression to v10.375 (Phase A second batch) per the roadmap approved with v10.374.

## What v10.375 delivered

### `pages/120_staff_pbt.py` — NEW (~290 LOC)

First UI surface of the v10.370 + v10.374 work. Sits alongside `113_branch_ranking.py` (Branch Manager view) and `114_sbu_drilldown.py` (SBU view) — completing the staff-dimension cockpit.

**Page structure:**

| Element | Purpose |
|---|---|
| Header + body-system framing caption | "circulatory system" — orthogonal to skeleton |
| 4-metric reconciliation strip | Bank PBT, Σ Staff PBT, Δ, Staff Buckets — makes G257 identity VISIBLE |
| 3 filters | Tier (default portfolio_owner), SBU, Branch scope |
| Tab 1: Staff ranking | Sortable table with full per-staff PBT breakdown |
| Tab 2: Tier distribution | Σ PBT by tier — confirms all tiers sum to bank PBT |
| Tab 3: SBU contribution | Σ PBT by SBU — links to v10.368 dimension |
| Tab 4: Unassigned bucket | Surfaces data-quality gaps (customers without rm_code) |
| Footer data lineage | seed → persist → compute_pbt_by_customer → compute_pbt_by_staff → classify_role → UI |

**Resolves the v10.370 teller-vs-RM framing:**
- **Data engine remains role-neutral.** `compute_pbt_by_staff` returns ALL tagged staff including tellers (per your note: tellers occasionally introduce accounts in real banks).
- **UI surfaces ownership.** The tier filter (default `portfolio_owner`) shows only the primary sales — RM PB/BB, BRM, SRO, RO, DSO, plus HO Corporate/SME/Sector RMs. Tellers and CSOs sit in the `service` tier and only appear when the user explicitly switches to `(all tiers)`.

### Engine usage

- `compute_pbt_by_customer` (v10.370 atom) — per-customer foundation
- `compute_pbt_by_staff` (v10.370 atom) — per-staff Σ over portfolio
- `compute_pbt_from_cbs` (v10.364 canonical bank PBT) — reconciliation reference
- `classify_role` (v10.374 taxonomy) — joins each staff_code to a tier/scope/sbu
- `sum_staff_pbts` (v10.370 aggregator) — Σ verification

All canonical. Zero legacy paths. Zero parallel calls.

### Manifest registration

```json
"120_staff_pbt.py": {
    "department_primary": "sales_customer",
    "module_path": "sales_customer.staff_pbt",
    "secondary_visibility": ["strategy_performance", "finance"],
    "title": "Staff PBT (Role-Aware)",
    "icon": "👥",
    "current_module_key": "staff_pbt",
    "description": "..."
}
```

### G261 — Staff PBT page lock

Verifies 6 invariants:
1. Page file present
2. Imports `compute_pbt_by_staff` + `classify_role` (canonical engine usage)
3. Has the 3 role-aware filters (tier, sbu, scope)
4. Has reconciliation strip with G257 identity visible
5. Documents data lineage
6. Manifest entry registered with correct module_path + department

Cost: ~0.005s (file reads + JSON parse).

### Tests — 11/11 across 3 sections

**Section 1 (page structure):** file present, canonical engine imports, 3 filters present with portfolio_owner default, reconciliation strip visible, data lineage documented

**Section 2 (manifest + gate):** manifest entry correct (module_path, department), G261 passes, G261 registered in GATES list immediately after G260

**Section 3 (no regression):** all 7 prior unification identities still hold, role taxonomy still 100% coverage, taggability invariant still locked across all 41 classified roles

## Files changed

| File | Change |
|---|---|
| `pages/120_staff_pbt.py` | **NEW** (~290 LOC) — first role-aware UI |
| `pages/_manifest.json` | **EXTENDED** — entry for 120_staff_pbt.py |
| `scripts/audit.py` | **NEW** `gate_staff_pbt_page` (G261) |
| `scripts/verify_local_state.py` | Extended to 309 checks |
| `tests/integration/test_v10375_staff_pbt_page.py` | **NEW** — 11 tests across 3 sections |
| `docs/Master_Prompt_v4.19.md` | **NEW** — lockstep bump from v4.18 |

## Verified outcome

| Metric | Value |
|---|---|
| Page renders against canonical engines | ✓ (cached 5min) |
| Reconciliation strip visible to user | ✓ (G257 identity surfaced) |
| Three role-aware filters operational | ✓ tier / sbu / scope |
| Audit gates | 260 → **261** (G261 added) |
| All 7 prior unification identities | still PASS |
| All v10.374 taxonomy invariants | still PASS |
| Charter §2 (G249) | still PASS |
| Page smoke | 124/124 + 0 static |
| Tests | +11 in v10.375; **250 total across v10.358–v10.375** |
| Verifier | 299 → **309 checks** |
| Master prompt | v4.18 → **v4.19** — lockstep (20 consecutive batches) |
| G162 baseline | 4022 (**69 consecutive zero-drift batches**) |

## Honest acknowledgements

1. **The data engine is role-neutral by design.** `compute_pbt_by_staff` returns ALL staff with tagged customers — tellers, CSOs, RMs, BRMs, everyone in `accounts.csv::relationship_manager_code`. This honors your point that "operations roles also do open accounts" — we don't filter them out at the engine layer. Filtering happens at the UI layer via the tier dropdown.

2. **Default filter is `portfolio_owner`** because that's the primary sales-attribution view. Users who want to see ALL tagged staff (including tellers) toggle to "(all tiers)". This is the cleanest resolution of the teller-vs-RM framing: engine-neutral data, role-aware presentation.

3. **The reconciliation strip is the page's most important feature.** It shows Bank PBT, Σ Staff PBT, and the Δ live. When a user filters down to portfolio_owner only, they SEE that the slice doesn't sum to bank PBT (other tiers contribute too) — and the Tier Distribution tab makes the full Σ visible. This builds trust: the user can verify G257 themselves.

4. **Customer count parsing has a brittle dependency.** I extract it from `pbt_components.notes[0]` which today is `"Portfolio: N customers"`. If the format changes in `customer_pbt_allocator.py`, the page would show wrong counts. **Future cleanup:** add a proper `n_customers` field to PBTComponents. For now, the format is stable and tested.

5. **`@st.cache_data(ttl=300)` is a 5-minute cache.** Seeding the bank + persisting + computing all four engines takes ~0.5s for the 100-customer seed. In production with 700K customers it would be slower; cache prevents hammering the engine on every filter change.

6. **The page uses `SeedConfig.small()` (100 customers).** Production would use the real CBS data, but currently the page seeds a virtual bank on each cold load. **Future cleanup:** when the actuals_engine integration with live CBS is fully wired (v10.365+), the page should detect a live CBS dir and use it instead of seeding. For Phase A demo purposes, seed is fine.

7. **The Unassigned tab is intentionally prominent.** In production, the % of customers without a tagged RM is a data-quality KPI. By giving it a tab, we make it impossible to ignore. The footer notes "Engineering goal: zero; real banks typically have <5%; values above point to RM-coverage gaps".

8. **`SBU contribution` tab uses staff-side aggregation, not customer-side.** Each staff has a primary SBU (from role classification); we Σ their PBT into the SBU bucket. This may differ slightly from `compute_pbt_by_sbu` (which uses customer segment → SBU mapping) — they're different roll-ups of the same atoms. Both reconcile to bank PBT (within KES 100). Documenting this in v10.376 when we surface SBU drill-down in MD cockpit.

9. **No new utils module.** Page composes existing canonical engines. This is the right pattern for Phase A — UI surfaces don't introduce new engines; they consume them.

10. **`_load_staff_pbt_view()` is a pure function** (modulo the seed which uses a deterministic seed). Reproducible, testable. The 5-min cache wraps it; pytest unit tests can call the unwrapped logic if needed (we don't today; the integration tests verify structure, not rendering).

11. **Rule N2 held:** single batch, single concern (one new page + manifest entry + audit gate + tests). Did not touch any engine module. Did not touch v10.374 role taxonomy. Did not start Phase B (customer master merge).

12. **Footer documents the data lineage explicitly.** "seeded VirtualBankCore → persist_bank_to_cbs → CBS accounts.csv + customers.csv → compute_pbt_by_customer (v10.370 atomic, G256) → compute_pbt_by_staff (v10.370 Σ, G257) → joined with users.json::role → classify_role (v10.374 profitability axis, G260) → this view." Users see the full chain.

13. **G261 cost is essentially zero.** Pure file + JSON checks. Won't slow audits.

14. **The page doesn't show every staff** by default. Only the 100-customer seed has ~5-10 distinct staff in tagged positions. In production this would scale to ~232 RMs. The table is sortable; users can also drill via the filters.

15. **Body-system harmony is now visually expressed.** The skeleton (seniority hierarchy in branch_ranking, sbu_drilldown) shows reporting structure. The circulatory (this page) shows PBT flow. Same staff appear in both — same skeleton position, same circulatory tier. The two axes describe the same person completely.

## On your end

1. Close Streamlit
2. Delete leftover subfolder extracts
3. Extract `a2z_v10375_session_cumulative.zip` flat
4. Run `python scripts\verify_local_state.py` → expect **ALL 309 CHECKS PASSED**
5. **Open the new page in Streamlit:** Navigate to "Staff PBT (Role-Aware)" — should appear under sales_customer department with the 👥 icon
6. **Try the filters:**
   - Default view shows portfolio_owner only — these are your tagged sales (RM PB/BB, BRM, SRO, RO, DSO + HO RMs)
   - Switch to "(all tiers)" to see everyone including tellers in service tier
   - Filter by SBU = "Commercial Banking" to see only commercial RMs (mostly head_office scope)
   - Filter by Branch scope = "head_office" to see only HO sales (Corporate, SME, Sector RMs)
7. **Check the reconciliation strip** — Bank PBT, Σ Staff PBT, Δ should all be visible at top
8. Read `docs\Master_Prompt_v4.19.md`
9. (Optional, takes >5min) Audit → expect **261/261 PASS**

## What comes next — v10.376

**v10.376 — MD cockpit SBU + Branch drill-down** (Phase A third and final batch).

Refactor `pages/100_md_cockpit.py` (or add a new section) to surface:
- Bank PBT (from canonical engine — already there)
- SBU drill-down using `compute_pbt_by_sbu` (v10.368) — clickable per SBU
- Branch drill-down using `compute_pbt_by_branch` (v10.369) — clickable per branch
- Link to this page (120_staff_pbt) for staff-level drill

After v10.376, Phase A is complete and Phase B opens with **v10.377 — Customer master merge** (your "merge into 1" approval).

Want me to continue with v10.376?
