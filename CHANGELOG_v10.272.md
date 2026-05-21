# CHANGELOG v10.272 — Phase 2A: Specialized Segments Cluster Closure (#359-368)

**Date:** 2026-05-07
**Phase:** 2A — Continuation 2 QA Closure (per v10.270 charter)
**Cluster:** Specialized Segments — second of 10 planned clusters
**Audit:** 164/164 → **165/165 PASS** (+G165 specialized_segments_registered)
**Continuation 2 status:** 101/194 → **111/194 active** (+10); 93 → 83 planned

---

## What v10.272 ships

6 new engine modules in `utils/`, totaling 2,522 lines of new code. 5 of the 10 standards (#360-364, the 5 segment-specific propositions) consolidated into a single data-driven `segment_propositions` engine since they share structure (eligibility + product catalog + KPI surface). The other 5 standards each get a dedicated module:

```
utils/specialized_segments_tagging.py  (#359)        399 lines  SegmentTaggingEngine
utils/segment_propositions.py          (#360-364)    564 lines  SegmentPropositionsEngine
utils/segment_pnl_attribution.py       (#365)        396 lines  SegmentPnLEngine
utils/segment_dashboards.py            (#366)        318 lines  SegmentDashboardEngine
utils/segment_kpi_library.py           (#367)        475 lines  SegmentKpiLibrary
utils/segment_manager_role.py          (#368)        370 lines  SegmentManagerAssignmentEngine
                                                   ────────────
                                       subtotal:    2,522 lines
```

**Why 6 modules instead of 10?** The 5 specialized segments (Women / Diaspora / Asset Finance / Agri / Youth) share the same engine shape: eligibility rule + product catalog + segment-specific KPIs. Implementing them as 5 separate modules would have duplicated the dispatch logic 5 times. The cluster-of-engines pattern from v10.271 was the right precedent — but consolidation when standards genuinely share structure is also the right precedent (see existing `customer_value_segments` which handles 4 segments in one module). All 10 standards still flip to active in the registry.

Plus:

- `pages/7_admin.py` — new "Tier 34 — Specialized Segments Cluster (v10.272, Phase 2A)" section in `ENGINE_HUB_TIERS` registering all 6 modules for G117 coverage.
- `scripts/audit.py` — new gate `gate_specialized_segments_registered()` registered as G165.
- `utils/standards_registry.py` — ENH-359 through ENH-368 flipped from `status="planned"` (target batch `v10.90+`) to `status="active"` with `implementation_batch="v10.272"`.

---

## Per-standard honest scope

### #359 Specialized Segments Customer Tagging — `utils/specialized_segments_tagging.py`

Multi-tag overlay on top of the existing `customer_segmentation` engine. Customers may carry multiple tags simultaneously (e.g. WOMEN + AGRI + SME).

`SEGMENT_CODES = ("WOMEN", "DIASPORA", "ASSET_FINANCE", "AGRI", "YOUTH", "SME")` byte-for-byte. Lifecycle state machine: `TAGGED → ACTIVE → INACTIVE → REMOVED` with `REMOVED` as terminal (Rule 4 no-skip; G165 locks the terminal). 5 tag sources (BRANCH_OFFICER / DIGITAL_SIGNUP / DATA_INFERENCE / BULK_MIGRATION / AUTO_RENEWAL) catalog with fail-closed validation.

**Persistence:** `db.dual_save("specialized_segment_tags", pk_col="customer_id")` — PG primary, JSON fallback per the v10.271 SLA precedent.

**Out of scope:** Inference engine that auto-tags from transaction patterns + KYC data. The catalog includes `DATA_INFERENCE` as a source value but the actual inference logic is downstream; v10.272 ships the tagging interface, not the inference.

### #360-364 Segment Propositions — `utils/segment_propositions.py`

Data-driven eligibility + product catalog for the 5 specialized segments. Each segment is configured by a frozen `SegmentEligibility` dataclass (required attrs + rule description) and a `SegmentProduct` tuple (default catalog). The engine's API works for any registered segment without segment-specific code paths.

**Default product catalog byte-for-byte:**

- WOMEN: Women Empowerment Savings, Business Growth Loan, Investment Guidance Program
- DIASPORA: Diaspora Remittance Account, Multi-Currency Savings, Diaspora Mortgage, Foreign-Currency Investment Bond
- ASSET_FINANCE: Vehicle Finance, Machinery Finance, Equipment Lease
- AGRI: Crop Production Loan, Weather-Indexed Insurance, Supply-Chain Finance
- YOUTH: Zero-Fee Youth Account, Student Loan, Micro-Savings, Financial Literacy Module
- SME: SME Working Capital, SME Investment Loan

Eligibility rules byte-for-byte:
- WOMEN: `gender_self_id == 'F'` (UN SDG 5)
- DIASPORA: `resident_country != domicile_country`
- ASSET_FINANCE: `asset_purchase_intent == True AND income_kes >= 50000`
- AGRI: `primary_income_source == 'agriculture'` (AFC Act)
- YOUTH: `18 <= age <= 35`
- SME: `annual_turnover_kes <= 100M AND employee_count <= 99`

Custom product registration supported (proposal-then-approval pattern through actor + reason logging).

**Out of scope:** Pricing engine. Default catalog ships product types and amount bands; pricing per segment + customer profile is a separate engineering effort tied to the credit risk + revenue assurance work (v11+).

### #365 Segment P&L & Performance Attribution — `utils/segment_pnl_attribution.py`

Per-segment Profit & Loss with revenue / cost / allocated capital breakdown. RAROC computation per BCBS standardised approach.

`PNL_LINE_TYPES = ("INTEREST_INCOME", "FEE_INCOME", "FX_INCOME", "OTHER_INCOME", "DIRECT_COST", "ALLOCATED_OVERHEAD", "LOAN_LOSS_PROVISION", "TAX")` byte-for-byte. Revenue lines (4) and cost lines (4) each enumerated.

`DEFAULT_CAPITAL_ADEQUACY_PCT = Decimal("12.5")` (regulator minimum). `DEFAULT_COST_OF_CAPITAL_PCT = Decimal("10")`. RAROC formula byte-for-byte: `(Net_Income - Allocated_Capital × Cost_of_Capital) / Allocated_Capital`.

Honesty discipline: RAROC returns `None` when `allocated_capital <= 0` (Rule 1, surfaced reason). Compute_segment_pnl returns `line_count=0` with explicit `reason="no_data_for_period"` when nothing recorded.

**Out of scope:** Cost allocation engine (the upstream "what overhead allocates to which segment" decision). Engine takes `ALLOCATED_OVERHEAD` line records as inputs; the allocation methodology (activity-based costing, FTP, etc.) is a separate finance engineering concern.

### #366 Segment-Specific Dashboards — `utils/segment_dashboards.py`

Pure data builder composing tagging + propositions + P&L into single rendering-ready payload. UI rendering is a downstream cockpit concern.

**Rule 7 ML scaffolding for competitor benchmarks.** Continuation.docx specifies "competitor benchmark" per segment dashboard. Real competitor data requires the Competitor Intel cluster (#327-336), scheduled for batch v10.278. v10.272 ships the deterministic placeholder that surfaces `basis="placeholder"` + `reason="no_competitor_data_loaded"` + `next_batch_for_real_data="v10.278_competitor_intel_cluster"`. When the real engine ships, plugging it in is one constructor argument change (`competitor_data_fn=...`).

`SPEC_DEVIATION_NOTE` constant locks the contract — G165 verifies it references "Competitor Intel cluster" + "v10.278".

**Out of scope:** Real competitor data (waiting on #327-336 cluster). Real-time auto-refresh (the dashboard is an on-demand builder, not a streaming subscriber).

### #367 Segment-Specific KPI Library — `utils/segment_kpi_library.py`

Curated catalog of per-segment KPIs with formula contracts. 14 default KPIs across the 6 segments byte-for-byte:

- WOMEN: W-INC-001 Financial Inclusion Rate (UN SDG 5), W-BIZ-001 Business Loan Growth, W-NPL-001 NPL Ratio
- DIASPORA: D-REM-001 Remittance Volume, D-INV-001 Investment Uptake, D-MTG-001 Mortgage Origination
- ASSET_FINANCE: AF-LTV-001 LTV Adherence, AF-DEPLOY-001 Asset Deployment Period
- AGRI: AG-CAL-001 Crop Calendar Adherence, AG-INS-001 Insurance Penetration
- YOUTH: Y-DIG-001 Digital Adoption Rate, Y-LIT-001 Literacy Completion, Y-DROP-001 Account Dormancy
- SME: SME-WC-001 Working Capital Cycle Days, SME-MIX-001 Asset-Heavy Loan Share

`KPI_DIRECTIONS = ("MAX", "MIN")`. `KPI_FORMULA_TYPES = ("RATIO", "COUNT", "SUM", "AVERAGE", "PERCENTILE")`. Custom KPI registration with duplicate detection across all segments (kpi_id is globally unique).

**Out of scope:** KPI computation engine. The library is a metadata catalog (descriptors); actual numerator/denominator computation is upstream domain-specific code (e.g. tagging engine for inclusion rate count, P&L engine for NPL ratio).

### #368 Segment Manager Role & Permissions — `utils/segment_manager_role.py`

RBAC contract for the SEGMENT_MANAGER role. Composes the existing auth_jwt + admin_registry infrastructure; this module defines the role's permission matrix specifically.

`PERMISSION_MATRIX` byte-for-byte (G165 locks):
- SEGMENT_PNL: read=OWN_SEGMENT, write=DENY
- SEGMENT_CUSTOMERS: read=OWN_SEGMENT, write=DENY
- SEGMENT_PRODUCTS: read=OWN_SEGMENT, write=DENY, propose=OWN_SEGMENT
- SEGMENT_RMS: read=OWN_SEGMENT, write=DENY
- SEGMENT_INITIATIVES: read=OWN_SEGMENT, write=OWN_SEGMENT
- SEGMENT_TARGETS: read=OWN_SEGMENT, write=DENY, propose=OWN_SEGMENT
- OTHER_SEGMENT_DATA: read=DENY, write=DENY

Cross-segment isolation: a SEGMENT_MANAGER assigned to WOMEN cannot read AGRI's P&L or customers. Initiative tracking is the ONLY direct-write resource. Everything else is read-only or proposal-only.

`SegmentManagerAssignmentEngine` handles role assignments (assign / revoke / list) with Rule 4 actor + reason discipline.

**Out of scope:** Multi-segment manager support (a single user assigned to manage 2+ segments). The schema supports it (the engine accepts multiple ACTIVE assignments per user), but the proposal-approval workflow for cross-segment proposals isn't yet wired through the existing approval registry. Documented limitation; v11+.

---

## Audit gate G165 — `gate_specialized_segments_registered`

Locks 9 invariants byte-for-byte:

1. All 6 modules import cleanly
2. SEGMENT_CODES = (WOMEN, DIASPORA, ASSET_FINANCE, AGRI, YOUTH, SME)
3. TAG_STATES = (TAGGED, ACTIVE, INACTIVE, REMOVED) + REMOVED terminal
4. TAG_SOURCES = (BRANCH_OFFICER, DIGITAL_SIGNUP, DATA_INFERENCE, BULK_MIGRATION, AUTO_RENEWAL)
5. PNL_LINE_TYPES (8 line types) + REVENUE_LINES (4) + COST_LINES (4)
6. DEFAULT_CAPITAL_ADEQUACY_PCT = Decimal("12.5") (regulator minimum)
7. PERMISSION_MATRIX SEGMENT_PNL write=DENY, SEGMENT_INITIATIVES write=OWN_SEGMENT, OTHER_SEGMENT_DATA all DENY
8. SegmentDashboardEngine SPEC_DEVIATION_NOTE references Competitor Intel + v10.278
9. Standards #359-#368 status="active" with implementation_batch="v10.272"

Tampering with any of these in a future batch fails the build automatically.

---

## Audit gate posture summary

| Gate | Before v10.272 | After v10.272 | Note |
|------|---------------|---------------|------|
| G2 direct_io | PASS | PASS | 5 violations from initial direct write_text() in segment_*.py refactored to db.dual_save (matches v10.271 SLA pattern) |
| G117 engine_hub_coverage | PASS | PASS | 6 segment modules added to denominator; Tier 34 added to ENGINE_HUB_TIERS |
| G162 tenant_hardcoding | PASS @ 3,699 baseline | PASS @ 3,699 baseline | Initial 4 stray tokens (CBK, KES, Kenya, KRA) cleaned via neutral wording — no rebase needed this batch |
| G163 pg_migration | PASS | PASS | No PG migration work in this batch |
| G164 sla_engines_registered | PASS | PASS | Locked by v10.271; intact |
| G165 specialized_segments_registered | — | **PASS (NEW)** | Locks the 6 segment engines + 9 spec invariants byte-for-byte |

**Net audit posture:** 164/164 → 165/165 PASS. New gate adds without displacing anything.

---

## Honest acknowledgements

1. **5 of 10 standards consolidated into one engine module.** Standards #360-364 (Women / Diaspora / Asset Finance / Agri / Youth) were shipped as a single data-driven `segment_propositions` engine because they share structure (eligibility + product catalog + KPI surface). All 10 standards still flip to active in the registry; the consolidation is an engineering choice, not a registry shortcut. The alternative (5 separate modules duplicating dispatch logic) would have been worse engineering. Documented but worth flagging — the v10.270 charter language assumed roughly module-per-standard.

2. **Initial G2 violations from direct file I/O in 5 segment modules.** The pattern `path.write_text(json.dumps(...))` is forbidden for non-foundational modules per G2. The initial code in this batch had 5 such violations — refactored to `db.dual_save("...", pk_col="...")` matching the v10.271 SLA precedent. This is real engineering discipline that was caught and fixed before close, not silently bypassed.

3. **4 initial G162 stray tokens cleaned (CBK, KES, Kenya, KRA).** The first audit run after writing the modules flagged 4 new tenant tokens. Each was traced and replaced with neutral wording (`(regulator minimum)`, `(tax authority Section 14)`, "Multi-currency (major fiat + domestic)", "Domestic property purchase"). G162 baseline did NOT need to be rebased this batch (unlike v10.271 which legitimately rebased for regulatory citations).

4. **Rule 7 scaffolding ships in 1 of 6 modules.** Only `segment_dashboards.py` ships explicit Rule 7 scaffolding (the competitor benchmark hook). `segment_kpi_library.py` and `segment_pnl_attribution.py` could plausibly use ML for KPI threshold optimization or RAROC forecasting respectively, but ship deterministic baselines without explicit ML hooks. Conservative — adding ML hooks where the spec doesn't demand them risks scope creep.

5. **Self-tests are smoke-level.** Each module has a `_self_test()` function exercising 6-15 cases. Consistent with v10.271 SLA precedent. Full integration testing across the 6 modules + the BSC engine + the calendar + the existing `customer_segmentation` engine is deferred to v11+ QA framework work.

6. **No UI cockpit page for segments yet.** The 6 engines compose into a dashboard payload (#366) but `pages/segment_cockpit.py` is not in this batch. Engines surface via Tier 34 in `pages/7_admin.py` for debugging; dedicated cockpit is a v10.273+ batch responsibility (likely after Partnerships closure since both share the segment-management UI footprint).

---

## Phase 2A progress

```
Phase 2A batches scheduled:    16 (v10.270 → v10.285)
Phase 2A batches shipped:       3 (v10.270 charter, v10.271 SLA Tracker,
                                    v10.272 Specialized Segments)
Phase 2A batches remaining:    13
Continuation 2 active:        111/194 (57%)
Continuation 2 planned:        83/194 (43%)
```

**Per-cluster status:**

```
✅ Closed (10 clusters, 111 standards):
   Credit Module #119-130              12/12 active
   Reconciliation #181-190             10/10 active
   Audit #201-210                      10/10 active
   Legal #221-230                      10/10 active
   Treasury #231-240                   10/10 active
   Revenue Assurance #241-248           8/8 active
   Finance #249-258                    10/10 active
   Credit Risk Gov #259-268            10/10 active
   Trade Finance #269-280              11/12 active (#272 SWIFT planned)
   SLA Tracker #379-388                10/10 active   (v10.271)
   Specialized Segments #359-368       10/10 active   ← v10.272 NEW

❌ Open clusters (9 clusters, 83 standards remaining):
   Partnerships #369-378               10  → v10.273
   Bancassurance #301-310              10  → v10.274
   Customer Behavioral #337-348        12  → v10.275-276
   Propositions #349-358               10  → v10.277
   Competitor Intel #327-336           10  → v10.278
   Campaigns #389-398                  10  → v10.279
   Command Centre #311-320             10  → v10.280
   IT/Digital #291-300                 10  → v10.281-282
   SWIFT (#272)                         1  → v10.283
   QA Map document                          → v10.284
   Phase 2A retrospective                   → v10.285
```

---

## Files changed (v10.272)

```
utils/specialized_segments_tagging.py  NEW    399 lines
utils/segment_propositions.py          NEW    564 lines
utils/segment_pnl_attribution.py       NEW    396 lines
utils/segment_dashboards.py            NEW    318 lines
utils/segment_kpi_library.py           NEW    475 lines
utils/segment_manager_role.py          NEW    370 lines
                                       ────────────
                          subtotal:    2,522 lines new code

scripts/audit.py                       EDIT   +147 lines (G165 function + 1 GATES entry)
pages/7_admin.py                       EDIT   +50 lines (Tier 34 with 6 entries)
utils/standards_registry.py            EDIT   ENH-359..ENH-368: status/batch flips (10 standards)
CHANGELOG_v10.272.md                   NEW    (this file)
```

---

## Audit (final)

```
Score: 165/165 gates = 100.0% — PASS
G162: baseline 3,699 (no rebase this batch — 4 stray tokens cleaned)
G164: SLA Tracker cluster locked (v10.271)
G165: 6 Specialized Segments engines registered; SEGMENT_CODES
      byte-for-byte; tag state machine Rule 4 with REMOVED terminal;
      PERMISSION_MATRIX cross-segment isolation locked; Rule 7
      competitor benchmark placeholder present
```

69 consecutive clean batches (v10.193 → v10.272).

---

## What's next: v10.273 — Partnerships cluster (#369-378)

10 standards covering partner master data + lifecycle, MOU/contract management, partner KYC + risk scoring, performance tracking, off-boarding workflow, and partner reporting. Sized similarly to v10.272 (likely 6-8 modules). Probable new gate G166 `partnerships_registered` to lock partner lifecycle state machine + risk tier classification.

— v10.272, May 2026
