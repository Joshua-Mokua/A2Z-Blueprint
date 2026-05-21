# CHANGELOG v10.143 — ENH-132 Product Lifecycle Management

**Status:** **PHASE 1E PRODUCT 2/10 ACTIVE.** v10.142 opened the module with ENH-131; v10.143 ships the second engine — stage-gate process management with approval matrix, automated criteria evaluation, and sunset candidate detection.

**Audit:** `Score: 146/146 gates = 100.0% — PASS` (quoted from `python scripts/audit.py`). No new gate added — engine-level drop. **G142 anti-drift floor ratcheted continuation_doc active 67 → 68**. G144 264/264 STABLE; G145 15/15; G146; G117 unchanged. Engine self-tests 152/152. v10.143 tests 26/26 pass via inline runner.

---

## What this drop ships

| Artifact | Lines | Purpose |
|---|---|---|
| `utils/product_lifecycle.py` | ~600 | NEW. ProductLifecycleEngine with 9 public methods + 2 frozen result dataclasses |
| `data/product_lifecycle.json` | 16 entries | NEW seed. Per-product current_stage + transitions log + pending approvals |
| `data/product_stagegate_config.json` | ~30 | NEW seed. Bank-overridable thresholds + approval matrix |
| `utils/standards_registry.py` | +1 line | ENH-132 status flipped planned → active |
| `pages/7_admin.py` | +25 lines | Tier 4B extended with second engine entry |
| `tests/test_product_v10_143.py` | ~310 | NEW. 26 tests across 9 classes |
| `docs/Master_Prompt_v3.36.md` | ~1100 | Anti-drift sync v3.35 → v3.36 |
| `SCOPE_LEDGER.md` | updated | v10.143 row + status block |
| `CHANGELOG_v10.143.md` | this file | This document |

---

## The engine — `utils/product_lifecycle.py`

Per Continuation.docx Standard #132: "Stage-gate lifecycle with automated gates, approvals, and sunset criteria."

### Eight canonical stages

```
IDEATION → BUSINESS_CASE → DEVELOPMENT → LAUNCH → GROWTH → MATURITY → DECLINE → SUNSET
```

SUNSET is reachable from any stage (per CBK product-rationalization governance — a product can be sunset at any maturity if conditions warrant) but ONLY via explicit Product Head + CEO approval.

### Approval matrix (config-driven)

| Transition | Required approvers |
|---|---|
| IDEATION → BUSINESS_CASE | product_head |
| BUSINESS_CASE → DEVELOPMENT | product_head, risk_head, finance_head |
| DEVELOPMENT → LAUNCH | product_head, compliance_head, ops_head |
| LAUNCH → GROWTH | (auto when book ≥ 1B + customers ≥ 1000) |
| GROWTH → MATURITY | (auto when growth_rate ≤ 5%) |
| MATURITY → DECLINE | (auto when growth_rate < 0) |
| DECLINE → SUNSET | product_head, ceo |

All thresholds + approver lists are config-overridable via `data/product_stagegate_config.json`.

### Public methods

- `get_product_stage(product_id)` — current stage + since timestamp
- `get_stage_history(product_id)` — chronological transition log
- `evaluate_stage_gate(product_id, target_stage)` → `StageGateEvaluation` with per-criterion pass/fail + required approvers + missing_inputs trail
- `request_stage_transition(product_id, target_stage, requested_by)` — auto-lands when no approvals required + criteria met; otherwise creates pending entry
- `approve_transition(transition_id, approver_role, approver_id)` — records approval; lands the transition when ALL required approvers collected
- `reject_transition(transition_id, approver_role, reason)` — kills pending request; logs to transitions[] with `status="rejected"`
- `evaluate_sunset_criteria(product_id)` → `SunsetEvaluation`
- `get_sunset_candidates()` — list of products meeting sunset triggers
- `get_pending_approvals(approver_role=None)` — TTL-aware listing with `stale=True` flag for entries past 14 days

### Honesty discipline

- **Sunset never auto-triggers.** Engine returns `candidate_status="recommended_for_sunset_review"` or `"no_action"` — never `"auto_sunsetted"`. The decision requires explicit approver action.
- **Pending approvals TTL.** Entries past `pending_approval_ttl_days` (default 14) flag `stale=True` in operator queries — visible but not auto-purged.
- **Double approval same role rejected** with explicit `reason="role_already_approved:<role>"`.
- **Invalid approver role rejected** with the required-roles list returned for operator visibility.
- **Rejected transitions logged** in `transitions[]` (not silently dropped) with `rejections[]` sub-array preserving the rationale. Audit trail is the discipline.
- **Criteria evaluation surfaces missing_inputs.** When `customer_count` isn't available in `products.json`, the criterion is explicitly skipped — not silently treated as failed and not silently passed.
- **Pre-launch transitions have no quantitative criteria** — gated entirely by approval matrix; criteria_results stays empty + gate_open == True (vacuous truth, but documented).

---

## Self-test on real data

`python -m utils.product_lifecycle`:

- 16 products seeded in `data/product_lifecycle.json` from growth_rate heuristic: 8 DECLINE / 7 MATURITY / 1 GROWTH
- 0 sunset candidates (worst growth_rate is -3.8%, threshold is -20%)
- P001 → SUNSET evaluation: gate closed (-2.3% > -20% threshold), requires Product Head + CEO approval

---

## Companion engine relationship preserved

The existing `utils/product_profitability.py` (Standard #47, v5.52) has a `product_lifecycle()` method that **classifies position** from year-on-year revenue trends (LAUNCH / GROWTH / MATURITY / DECLINE). ENH-132 **manages the procedural stage-gate workflow** — transitions, approvals, sunset evaluation. The two are complementary:

- **#47 product_profitability.product_lifecycle()** → "where is this product right now in its trend curve?"
- **ENH-132 ProductLifecycleEngine** → "what's the formal stage state, who needs to approve the next transition, and which products meet sunset criteria?"

Both engines coexist. Neither replaces the other.

---

## Tests — `tests/test_product_v10_143.py`

26 tests across 9 classes:

- **TestEngineModule** (4) — exists / parses / class+dataclasses+CANONICAL_STAGES present / 9 required public methods
- **TestStageQueries** (2) — existing product / unknown product
- **TestStageGateEvaluation** (3) — unknown target stage fallback / invalid skip transition / sunset path from decline
- **TestTransitionFlows** (6) — approval-required full flow / partial approval stays pending / double-approval-same-role rejected / invalid-approver-role rejected / rejection flow / gate-closed-fails
- **TestSunsetEvaluation** (3) — unknown product / real product (recommendation only) / list returns valid items
- **TestPendingTTL** (1) — pending filtered by approver_role
- **TestSeeds** (2) — lifecycle seed exists+parses / stagegate config exists+parses
- **TestRegistryAndAdmin** (3) — ENH-132 active / ENH-131 still active / admin Tier 4B has both engines
- **TestNoRegression** (2) — audit gates intact / strategy module engines still active

All 26 pass via inline runner.

---

## Apply order

After v10.142:

```
1. utils/product_lifecycle.py             → utils/
2. data/product_lifecycle.json            → data/
3. data/product_stagegate_config.json     → data/
4. utils/standards_registry.py            → utils/   (ENH-132 flip)
5. pages/7_admin.py                       → pages/   (Tier 4B extension)
6. tests/test_product_v10_143.py          → tests/
7. docs/Master_Prompt_v3.36.md            → docs/
8. SCOPE_LEDGER.md                        → root
9. CHANGELOG_v10.143.md                   → root
```

`git add -A && git commit -m "v10.143 ENH-132 Product Lifecycle Management — Phase 1E 2/10"`. Then `python scripts/audit.py` should print `Score: 146/146 gates = 100.0% — PASS`.

---

## Phase 1E Product trajectory

| drop | scope | status |
|---|---|---|
| v10.142 | ENH-131 Product Profitability Intelligence | SHIPPED |
| **v10.143 (THIS)** | **ENH-132 Product Lifecycle Management** | **SHIPPED** |
| v10.144 | ENH-133 Customer Needs & Gap + ENH-134 Competitive Intel | next |
| v10.145 | ENH-135 CVP Builder + ENH-136 Ranking + ENH-137 Dynamic Pricing | |
| v10.146 | ENH-138 + ENH-139 + ENH-140 → MODULE CLOSE + G147 + cockpit + G148 | |

**v10.144 next-up:** ENH-133 Customer Needs & Gap Analysis + ENH-134 Competitive Intelligence for Products. Paired drop — both engines feed v10.145's CVP Builder so they ship together.

---

## Summary

ENH-132 ships a stage-gate process engine that sits alongside (not replaces) the existing #47 lifecycle classifier. The eight-stage canonical progression with config-driven approval matrix and recommendation-only sunset preserves the honesty discipline — no auto-sunsets, no silent role-bypass, every approval recorded. Phase 1E now 2/10 active. v10.144 brings ENH-133 + ENH-134 as a paired drop.

**Quoting the audit script directly:** `Score: 146/146 gates = 100.0% — PASS`. v10.143 tests `26/26 pass`.
