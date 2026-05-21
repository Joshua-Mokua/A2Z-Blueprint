# A2Z MIS 360 — Architecture Document

**Version:** v10.38 (May 2026)
**Status:** Cross-cutting reference document. Auto-updated by `scripts/structure_audit.py`.

---

## Purpose

This document gives a domain-driven view of the codebase **without renaming, moving, or modifying any source files**. It complements the standards registry (`utils/standards_registry.py`) by mapping modules to business capabilities — not by spec number, but by business domain.

It is read alongside two machine-readable artifacts:

- `docs/module_map.json` — every module → primary domain + line count
- `docs/structure_audit_report.md` — current findings from the structural hygiene audit
- `docs/structure_audit_baseline.json` — locked baseline of HARD findings; G128 enforces no regression

---

## Anti-entanglement gates

Two layers of structural protection are in place:

| Gate | Type | Tool | What it locks |
|---|---|---|---|
| **G128** | Hard | `structure_audit_core.audit()` | Codebase shape: no new circular imports, no new layer violations beyond the captured baseline |
| **G1-G127** | Hard | `scripts/audit.py` | Semantic compliance: business rules, regulatory thresholds, arc closures |

Together: G1-G127 verify the engines do the right thing; G128 verifies the codebase stays the right shape as it grows.

---

## Layer model

| Layer | Path | May depend on |
|---|---|---|
| **L0 — Base** | `utils/db.py`, `utils/config.py`, `utils/core.py` | stdlib only |
| **L1 — Engines** | rest of `utils/` | L0 + other L1 modules + stdlib |
| **L2 — UI pages** | `pages/` | L0 + L1 + streamlit + stdlib |
| **L3 — Tooling** | `scripts/` | L0 + L1 + stdlib |
| **L4 — Tests** | `tests/` | anything |

**Forbidden edges (HARD-failing in G128):**

- `utils/` → `pages/` — engines must not depend on UI
- `utils/` → `scripts/` — engines must not depend on CLI tooling
- `scripts/` → `pages/` — CLI must not depend on UI

Currently zero layer violations. Locked.

---

## Domain model — current state

The following 11 domains organize the existing modules. This mapping is one **logical view** over the codebase — modules are not physically reorganized.

### Domain 1: Strategy & Execution

Strategic planning, target cascade, BSC scoring, profitability, board reporting.

Representative modules: `bsc_engine`, `kpi_library`, `target_cascade`, `cascade_engine`, `board_reporting`, `allocation_optimizer`.

### Domain 2: Customer & Relationship

Customer 360, behavioural intelligence, CRM/pipeline, churn prediction, digital origination, cards.

Representative modules: `pipeline_engine`, `opportunity_pipeline`, `churn_prediction`, `customer_360`, `cards`.

### Domain 3: Credit & Lending

Underwriting, alternative scoring, collections, NPL workout, ecosystem finance, retailer/value-chain finance, IFRS 9 ECL.

Representative modules: `credit_underwriting`, `credit_collections`, `kesonia_*`, `asset_impairment`.

### Domain 4: Products & Propositions

Product catalogue, propositions, bancassurance, deposits.

Representative modules: `product_house`, `propositions`, `bancassurance`.

### Domain 5: Risk & Compliance

ERM, climate risk, AML/KYC/sanctions, data protection, model governance, audit GRC, fraud, operational risk.

Representative modules: `climate_risk`, `climate_pd_overlay`, `model_governance`, `audit_core`, `audit_universe`, `audit_controls_issues`, `audit_dashboards_portal`, `business_intelligence`.

### Domain 6: Finance & Treasury

GL, treasury (ALM/IRRBB/liquidity), FTP, reconciliation, Islamic, agentic, capital, cross-asset rollup, climate-adjusted limits.

Representative modules (Treasury arc complete at v10.37):
- `treasury_alm` · `treasury_products` · `rwa_optimization` · `fund_transfer_pricing` · `cash_forecasting` · `treasury_dashboard`
- `islamic_treasury` · `treasury_agents` · `treasury_connectivity` · `treasury_digital_assets` · `treasury_unified_platform` · `climate_treasury_limits`
- `capital_adequacy` · `cost_allocation` · `channel_income`

### Domain 7: Operations & Support

Contact centre, procurement, SLA, CIMS, EDMS, dormancy, branch operations.

Representative modules: `cims`, `edms`, `dormancy`, `sla`, `branch_ops_excellence`, `channels_reliability`.

### Domain 8: Marketing & Sales

Customer + staff campaigns, competitor intelligence, partnerships, cross-sell bandit.

Representative modules: `cross_sell_bandit`, `campaign_*`, `competitor_intel`, `partnerships`.

### Domain 9: People & HR

People management: coaching, compensation, training, RBAC.

Representative modules: `coaching_intelligence`, `compensation_equity`, `training`, `learning_*`.

### Domain 10: IT & DevOps

ITSM, security, observability, vendor adapters (FlexCube).

Representative modules: `flexcube_adapter`, `flexcube_aggregator`, `flexcube_connection`, `itsm`.

### Domain 11: Cross-Arc Infrastructure

Cross-arc infrastructure with no single domain home: scenario harness, virtual bank simulation, standards registry, structure audit, API layer.

Representative modules: `scenario_simulator`, `virtual_bank_core`, `virtual_bank_simulator`, `standards_registry`, `structure_audit_core`, `api`, `auth_jwt`.

---

## Cross-arc bridges (intentional facades)

These modules deliberately compose other domains and have high incoming dependency counts **by design**. They are exempt from the god-module heuristic:

| Module | Bridges | Notes |
|---|---|---|
| `treasury_dashboard` | Treasury (5 engines) | ENH-238 — daily/board/regulatory pack aggregation |
| `treasury_unified_platform` | Treasury (7 engines) + Islamic + Digital | ENH-TRS-R4 MX.3-style facade |
| `climate_treasury_limits` | Climate × Treasury | ENH-TRS-R6 cross-arc bridge |
| `scenario_simulator` | All arcs | v10.36 cross-arc test harness |

---

## Base infrastructure (high-fan-in by design)

These modules are imported widely across the codebase **by design**. Exempt from god-module warnings:

| Module | Incoming | Why widely used |
|---|---|---|
| `utils.db` | 110 | Database access — used by every page + engine |
| `pages._shared` | 95 | Shared UI utilities (formatting, layout) |
| `pages._access` | 94 | Auth + RBAC checks on every page |
| `utils.core_audit` | 84 | Audit logging hook used throughout |
| `utils.config` | 27 | Configuration loaded everywhere |
| `utils.standards_registry` | varies | Consumed via introspection |

---

## Known structural debt

The structure audit captures a **baseline** of existing HARD findings that cannot grow. Current baseline (May 2026):

| Category | Count | Status |
|---|---|---|
| **CIRCULAR_IMPORT** | 3 | All involve `utils.core` ↔ `utils.actuals_engine` ↔ `utils.bsc_engine` / `utils.core_audit` / `utils.core_kpi`. Pre-existing; system runs because Python resolves them at runtime through deferred imports. |
| **LAYER_VIOLATION** | 0 | None — locked. |

### Identified god module: `utils.core`

`utils.core` at **6346 lines + 74 incoming + involved in 3 circular imports** is the genuine god module. It accumulated as a junk drawer over many batches.

**v10.38 decision:** do NOT refactor `utils.core` in this batch. The structural audit makes the issue visible; refactoring is a separate workstream that requires careful slicing along cohesive concerns. The **baseline mechanism prevents the situation from getting worse** while we plan the slice.

**Future direction:** when a future batch needs to extend `utils.core`, take the opportunity to extract the relevant cohesive subset into a focused module instead. The `utils.core` line count should trend down, not up.

### WARN-level findings (informational, not blocking)

- 6 god modules (after exemption): only `utils.core` remains
- 1 junk drawer: `scripts.audit` (15843 lines — inlines all 128 audit gates)
- 26 orphan modules (likely entry-point scripts or reflectively-loaded)
- 15 duplicate symbol definitions (mostly conventional helpers like `_test_*`, `format_*` — review on case-by-case basis)
- 8 size outliers (modules > 2000 lines)

---

## Anti-entanglement working agreement

These rules apply to every future batch:

1. **No new circular imports.** G128 fails the audit if any new cycle is introduced. Use protocols / callbacks / shared lower-layer types if circularity threatens.
2. **No new layer violations.** `utils/` → `pages/` is forbidden. `utils/` → `scripts/` is forbidden.
3. **Cross-arc bridges declared.** New facade modules that compose multiple domains add their short name to `structure_audit_core.CROSS_ARC_BRIDGES`.
4. **God modules require approval.** Any module exceeding 15 incoming dependencies that isn't already on the exemption list triggers a WARN. Convert to facade or extract subsets.
5. **Size discipline.** New modules over 2000 lines emit INFO; over 4000 lines emit WARN. Plan splits early rather than letting modules drift toward 6000+.
6. **Duplicate detection in code review.** New `class Foo:` or `def foo():` matching an existing module's symbol triggers WARN. Review for consolidation opportunity before merging.

The rules are mechanical, not aesthetic. The audit runs every batch automatically.

---

## What this document is NOT

- **Not a refactor plan.** It does not require any code reorganization.
- **Not a renaming initiative.** Standard numbers and module names stay as they are.
- **Not a comprehensive tutorial.** Engine details live in the engines themselves; this doc is a navigation aid.
- **Not aspirational.** It describes the codebase as it is today. Findings are the actual output of `structure_audit_core.audit()`.

---

## How to refresh this view

```bash
# Run structural audit; refresh report + module_deps.json
python3 scripts/structure_audit.py

# After intentional improvement, update the baseline
python3 scripts/structure_audit.py --capture-baseline
```

Both commands are read-only on the source code. Only the `docs/` artifacts are modified.
