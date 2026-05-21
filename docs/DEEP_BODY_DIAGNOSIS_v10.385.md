# Deep Body-Wide Diagnosis — A2Z MIS 360

**Version anchor:** v10.385 (May 2026)
**Per:** Joshua's directive at v10.383 wrap-up — *"once done you do a proper deep anlysis/diagonise of the entire body and we fix it"*

The previous batches (v10.367-v10.384) unified the circulatory organ, rescued the prioritization organ, and surfaced specific drift in individual subsystems. v10.385 is the **comprehensive body-wide health survey** — every organ examined, every drift catalogued, every silent failure surfaced, and a prioritized fix sequence proposed.

This is a diagnosis document. **v10.385 ships REVIEW ONLY — no code changes.** Subsequent batches v10.386+ execute the fixes under your approval.

---

## Part 1 — Executive summary: the body's vital signs

### 1.1 Body composition (size and shape)

| Tissue | Count | Status |
|---|---|---|
| Utility modules (`utils/*.py`) | **447** | substantial body |
| Pages (`pages/*.py`) | **124** | many organs |
| Integration tests | **105** | strong coverage in Phase B arc |
| Data files (`data/*.json`) | **208** | many state stores |
| KPI library (total) | **185 KPIs** | rich vocabulary |
| KPI library (active) | **52 KPIs** | most disabled |
| Cascade entries | **1,051 staff codes** | full hierarchy |
| Target rows | **~7,358** | comprehensive cascade |
| Audit gates | **270** | strong endocrine system |
| LOC (virtual bank alone) | **~5,609** | substantial seed engine |

### 1.2 Diagnostic vitals at v10.385 entry

| Vital sign | Reading | Healthy? |
|---|---|---|
| Verifier checks | 445/445 pass | ✓ |
| Phase B arc tests | 106/106 pass | ✓ |
| G162 audit baseline drift | 0 in 78 consecutive batches | ✓ |
| Master prompt lockstep | 29/29 consecutive batches | ✓ |
| Active §5.4 silent failures (known) | **2 documented, 1 fixed, 1 rescue underway** | partial |
| Customer master canonical adoption | **3/3 engine consumers** (page consumers not yet) | partial |
| KPI alias coverage | 178 of 193 resolved (92%) | ✓ |
| Class B orphans needing definition | **15** documented | needs work |
| Joshua decisions queued | **23** | awaiting input |

### 1.3 Top-line diagnosis

The body is **structurally healthy but has multiple unaddressed silent failures** and unmigrated consumer pages. The skeleton, endocrine, and circulatory systems are sound. The nervous and recognition systems are functioning but with documented drift. The prioritization organ is mid-rescue. The brain has accumulated unresolved decisions that need closure.

**There are no critical/fatal conditions.** All identified issues are tractable and fixable in 10-15 batches of disciplined work.

---

## Part 2 — Skeleton (organizational hierarchy + role assignment)

### 2.1 What this organ does

Defines the bank's shape: MD → Director → Head → Regional → Branch → individual staff. Tells every staff member which KPIs apply to them (`role_kpis`), which role they hold, who reports to whom, and where they sit in the cascade.

### 2.2 Current health

| Metric | Value |
|---|---|
| Roles in `role_kpis` | **227** |
| Roles in canonical taxonomy | **126** |
| Difference (aspirational roles?) | **101** |
| Cascade entries | 1,051 staff codes |
| Target rows | ~7,358 |

### 2.3 Findings

**Finding S1 — Role count mismatch (227 vs 126).** `kpi_library.json::role_kpis` has 227 role entries; the canonical role taxonomy from v10.374 has 126. The 101-role gap means roles exist in BSC config that don't exist in the org chart — either aspirational (planned but not staffed), historical (no longer used), or duplicates with slight name variations (e.g. "Branch Manager" vs "Branch Mgr"). **Severity: MEDIUM** — the body has phantom organs.

**Finding S2 — Specific role-name drift not catalogued.** The v10.380 deep review documented the count gap but didn't enumerate which 101 roles are the difference. **Severity: LOW** — easily surfaced when needed.

**Finding S3 — Org hierarchy file separate from KPI library.** `org_hierarchy_config.json` defines reporting lines; `kpi_library.json::role_kpis` defines KPI assignments. The two stores must agree on role names. **Severity: LOW** — currently agree, but no enforcement gate.

### 2.4 Diagnosis

The skeleton is **mostly intact, with phantom limbs**. Phantom limbs aren't immediately dangerous (they don't hurt anyone) but they should be documented or removed before they cause confusion in future cascade work.

### 2.5 Suggested fixes

| Fix | Effort | Batch |
|---|---|---|
| Enumerate the 101 phantom roles (which are aspirational vs duplicate vs obsolete) | Low | v10.395 |
| Add `role_status` field (active / aspirational / deprecated) per v10.381 Decision 6 | Low | v10.396 |
| Add audit gate that org_hierarchy_config and role_kpis agree on active role names | Low | v10.397 |

---

## Part 3 — Circulatory (profitability + PBT)

### 3.1 What this organ does

Tracks the bank's money. Computes bank PBT (Profit Before Tax), allocates it to SBUs, branches, customers, RMs. Recently unified through canonical engines.

### 3.2 Current health

| Metric | Value |
|---|---|
| Profitability modules | 13 in `utils/` |
| Canonical engines unified post-Phase B | customer + RM both use v10.378 |
| Bank PBT computation | works (live demo: KES -7.9B in v10.379 demo) |
| Customer + RM identity check | passes (G265 + G269) |

### 3.3 Findings

**Finding C1 — Phase B parallel-engines unification COMPLETE.** v10.381 (customer) + v10.383 (RM) both now consume `compute_unified_customer_master()`. The body's circulatory organ is fully wired through the recognition organ. **Severity: NONE — this is the win.**

**Finding C2 — RM-portfolio sizes are CBS-dependent.** Without CBS data on disk, the canonical RM lookup returns empty (no rm_codes in marketing intel). In production with full CBS data, RMs see their real portfolios. **Severity: LOW** — by design, but worth noting CBS data must be present for RM dashboards to populate.

**Finding C3 — Two separate process-wide caches** (one in `customer_profitability.py`, one in `rm_profitability.py`) both holding the same unified master. Acceptable for now but consolidation would save memory in production. **Severity: LOW** — efficiency, not correctness.

**Finding C4 — Bank PBT is currently negative (-KES 7.9B).** This is a real signal from the canonical engine, not a defect. It surfaces because management_accounts data shows costs exceeding income. **Severity: HIGH (business)** — but not a defect of the body. The body is correctly reporting the bank's state.

**Finding C5 — No reconciliation strip on customer-facing pages.** Customer 360 page doesn't show "Σ customer PBT = bank PBT within tolerance" though the engine could compute this. v10.382 review surfaced. **Severity: LOW** — defensive control missing.

### 3.4 Diagnosis

The circulatory organ is **in excellent shape post-Phase B**. The parallel-engines unification was the right architectural move. Bank-level numbers reconcile to allocated numbers. No silent failures.

### 3.5 Suggested fixes

| Fix | Effort | Batch |
|---|---|---|
| Consolidate the dual customer-master caches into one shared cache | Low | v10.398 |
| Add reconciliation strip to customer-facing pages | Medium | v10.388 (with admin pillar work) |
| Surface bank PBT trajectory in MD cockpit | Low | v10.389 |

---

## Part 4 — Nervous system (KPI flow + cascade + alias resolution)

### 4.1 What this organ does

Routes KPI definitions from library to roles to staff. Resolves aliases. Cascades targets. Translates "show me my BSC" into "here are your 6 KPIs with targets and actuals."

### 4.2 Current health

| Metric | Value |
|---|---|
| Total KPIs in library | 185 (52 active) |
| Active KPIs by pillar | Financial 38, Op Excellence 25, Customer Focus 18, Process 13, People 12, Risk 3 |
| Role-KPI assignments resolved (direct) | 159 |
| Role-KPI assignments resolved (via alias) | 19 |
| Role-KPI assignments unresolved (Class B orphans) | **15** |
| Unknown orphans | 0 ✓ |
| Cascade `deadline\|*` corruption keys | **1** (still present) |
| Total cascade entries | 1,051 staff codes |

### 4.3 Findings

**Finding N1 — 15 Class B orphan KPIs need definitions.** Role assignments reference these IDs but library doesn't define them. v10.380 documented them (e.g. NIM, CIR, ROE, NPS, DEP_GROWTH, DIGITAL_ACT, 5 LEGAL_*). v10.382 produced an implementation plan. **Severity: MEDIUM** — MD's BSC can't present a complete banking story until these land.

**Finding N2 — `deadline|*` cascade corruption still present.** 1 corruption key found in `target_cascade.json`. v10.380 documented; defensive filter in `kpi_alias_resolver` handles it. v10.381 Decision 4 proposed moving deadlines to `cascade_meta`. **Severity: LOW** — handled defensively but architecturally wrong.

**Finding N3 — KPI activation status conflicts.** Some KPIs have `active: null` (should be `false` per v10.381 Decision 5). Cleanup deferred. **Severity: LOW** — defensive code handles it.

**Finding N4 — 185 total KPIs, only 52 active.** The other 133 are noise — defined but unused. Library could be slimmed. **Severity: LOW** — clutter, not breakage.

**Finding N5 — Pillar `Process` and `Risk` exist as values but aren't in canonical 4 BSC pillars.** Some KPIs are pillar=Process (13) or pillar=Risk (3). The canonical BSC has only 4: Financial / Customer Focus / Operational Excellence / People & Learning. **Severity: MEDIUM** — likely needs reconciliation (do these roll up to Operational Excellence? Or is the pillar set expanding?). 

**Finding N6 — Alias coverage 92% (178/193).** Strong but not complete. The remaining 8% are the Class B orphans. **Severity: LOW** — same root cause as N1.

### 4.4 Diagnosis

The nervous system is **functioning but has documented signal-routing gaps**. Most signals route correctly (92%). Specific known-missing signals (Class B orphans) have an implementation plan ready to deploy. One small architectural defect (`deadline|*`) handled defensively but not properly fixed.

### 4.5 Suggested fixes

| Fix | Effort | Batch |
|---|---|---|
| Implement Tier 1 Class B KPIs (NIM/CIR/ROE/NPS/DEP_GROWTH) per v10.382 plan | Medium | v10.390 |
| Implement Tier 2 Class B KPIs (DIGITAL_ACT + 5 LEGAL_*) | Medium | v10.391 |
| Reconcile Process/Risk pillars with canonical 4 | Decision | v10.391 prereq |
| Move `deadline|*` to `cascade_meta` top-level | Low | v10.392 |
| Normalize `active: null` → `active: false` in library | Low | v10.393 |
| Deactivate or remove the 133 unused KPI definitions | Medium | v10.394 |

---

## Part 5 — Recognition organ (customer master + segmentation)

### 5.1 What this organ does

Knows the bank's customers. Unifies CBS-authoritative truth (rm_code, segment, branch) with marketing intel (analytics, propensity scores, NBA). Resolves identity across multiple data sources.

### 5.2 Current health

| Metric | Value |
|---|---|
| Unified master (no CBS) | 3,206 customers, all `marketing_only` |
| Unified master (with seed CBS) | 3,306 customers (100 CBS-only added) |
| Engine consumers using `compute_unified_customer_master` | **3** (canonical itself + customer_profitability + rm_profitability) |
| Pages consuming the canonical engine | **0** ⚠️ |
| Largest unmigrated consumer | `pages/34_customer360.py` (3,314 lines, 7 tabs) |
| Customer 360 disconnection identified | v10.382 |

### 5.3 Findings

**Finding R1 — Customer 360 (3,314 LOC) is the largest unmigrated consumer.** Reads `customer_intelligence.json` directly through its own `_load()` helper. Cannot see CBS-only customers. Cannot see provenance/lineage from v10.378. **Severity: HIGH** — this is the page literally about customers, and it doesn't see the bank's full customer base.

**Finding R2 — Two more pages read kpi_library directly** (not the customer master, but related). Cascade page (`pages/12_cascade.py` 2,988 LOC) and perform page (`pages/1_perform.py` 1,939 LOC). These don't strictly need the customer master but their direct reads of `kpi_library.json` mean they bypass the canonical accessor layer being built. **Severity: LOW** — works, but architecturally fragile.

**Finding R3 — Marketing intelligence has no `rm_code` field.** v10.383 exposed this. Pre-v10.383 RM dashboards always showed empty portfolios. The recognition organ couldn't connect customers to their assigned RMs without CBS data. Now fixed via canonical path. **Severity: NONE (resolved)** — documented as historical.

**Finding R4 — Segment data has two sources** (CBS KYC vs marketing intel) but conflicts aren't surfaced to operators. v10.378 captures the data but no UI shows "this customer's segment is Mass per CBS, Premier per marketing — conflict detected." **Severity: LOW** — data quality control gap.

**Finding R5 — Reconciliation identity holds** (G265 passes). The unified master accurately reconciles to CBS counts when CBS is present. **Severity: NONE — this is good.**

### 5.4 Diagnosis

The recognition organ is **architecturally sound but its largest analytical workbench (Customer 360) is disconnected from it**. Refactoring Customer 360 to consume the canonical master is the highest-leverage Phase C work.

### 5.5 Suggested fixes

| Fix | Effort | Batch |
|---|---|---|
| Add a preview "Canonical View" tab to Customer 360 (non-invasive first step) | Medium | v10.399 |
| Migrate Customer 360 Tab 1 (Customer Lookup) to canonical | Medium | v10.400 |
| Add Customer PBT panel using canonical engine | Low | v10.401 |
| Migrate remaining Customer 360 tabs progressively | Large | v10.402-v10.405 |
| Add segment-conflict surfacing UI | Low | v10.406 |

---

## Part 6 — Endocrine system (audit gates)

### 6.1 What this organ does

The body's regulatory feedback loop. 270 audit gates verify structural and behavioral invariants. The mypy-style baseline mechanism (G162) prevents regression. Every batch must pass all gates before shipping.

### 6.2 Current health

| Metric | Value |
|---|---|
| Total audit gates | **270** |
| Phase B gates (G249-G270) | 22 new in 2026 |
| G162 baseline | 4022 (78 consecutive zero-drift batches) |
| Critical-path gates smoke-checked per batch | 7-9 |
| Master prompt lockstep | 29 consecutive batches |
| Verifier checks | 445/445 |
| Audit run cost (full) | varies; G128 alone is ~10s |

### 6.3 Findings

**Finding E1 — Strong, healthy endocrine system.** 270 gates with consistent zero-drift baseline is excellent. The G162 mechanism (baseline diff like mypy strict) catches regressions before they ship. **Severity: NONE — major strength of the body.**

**Finding E2 — Gate coverage by organ is uneven.** Recent Phase B (v10.358+) added 22 gates focused on canonical engines. Earlier batches' gates focus on structural correctness. Some organs have many gates (skeleton, audit, profitability); some have few (UI behavior, end-user workflows). **Severity: LOW** — coverage gaps exist but no harm reported.

**Finding E3 — Some gates are slow (G128 ~10s, G249 ~0.4s, others sub-100ms).** A full audit run takes minutes. Per-batch we run a smoke subset. **Severity: LOW** — operational trade-off, not a correctness issue.

**Finding E4 — Gate retirement not formalized.** As organs evolve, some gates become redundant. No process to retire them. **Severity: LOW** — house-keeping, not breaking.

**Finding E5 — Older test suites have pre-existing failures.** v10.319-v10.344 tests have some failures unrelated to Phase B work. Documented but not yet investigated. **Severity: MEDIUM** — tech debt; could mask future regressions.

### 6.4 Diagnosis

The endocrine system is **the body's strongest organ**. The discipline of "no batch ships without gates green + baseline diff zero + lockstep prompt update" has produced 78 consecutive zero-drift batches. This is what makes everything else work.

### 6.5 Suggested fixes

| Fix | Effort | Batch |
|---|---|---|
| Investigate pre-existing v10.319-v10.344 test failures, repair or document | Medium | v10.407 |
| Formal gate-retirement process (deprecation markers in audit.py) | Low | v10.408 |
| Categorize gates by organ for coverage reporting | Low | v10.409 |

---

## Part 7 — Brain (constitution + decisions + master prompt)

### 7.1 What this organ does

The body's executive function. Constitution defines technical governance. Master prompt holds the running plan. Joshua's decisions provide the body's volition.

### 7.2 Current health

| Metric | Value |
|---|---|
| Constitution version | v10.377 (8-Part document) |
| Master prompt version | v4.28 (29 consecutive lockstep batches) |
| Active strategic reviews | 5 large documents (Customer 360, KPI Plan, Pillar Weights, Body Diagnosis, plus older PMF) |
| Joshua decisions queued | **23 documented** (C1-C7, K1-K8, W1-W8) |
| Decisions answered | Few — most awaiting input |

### 7.3 Findings

**Finding B1 — 23 decisions accumulated.** Each is well-specified with multiple options. The queue grows faster than it drains. Without your input, downstream batches (v10.390-v10.401) can't proceed in fully-correct order. **Severity: MEDIUM** — the body has unanswered questions about its own future.

**Finding B2 — Strong constitution.** The 8-Part document (v10.377) covers PostgreSQL truth, BSC contract, integration architecture, reconciliation, audit traceability, presentation layer, governance, flow principle. All recent batches comply. **Severity: NONE — major strength.**

**Finding B3 — Master prompt lockstep discipline holds.** 29 consecutive batches. Every batch updates the master prompt to reflect the current shipped state. This is what keeps cross-session continuity working. **Severity: NONE — major strength.**

**Finding B4 — Some decisions have recommended defaults (v10.381 doc).** If you don't answer, those recommendations could be used as Joshua-implicit-approval defaults. But that erodes the review-before-action principle. **Severity: LOW** — decision-process question, not a technical one.

**Finding B5 — Two large review documents not yet acted on** (v10.382 — Customer 360 review, KPI Plan). The system is over-documented vs under-implemented. **Severity: LOW** — bias toward review-before-action means more docs than code; this is by design but the gap shouldn't grow indefinitely.

### 7.4 Diagnosis

The brain is **strong but waiting on your input**. Constitution and master prompt are in excellent shape. The decision queue needs draining. Some batches can proceed without decisions (mechanical refactors, fixes for clear bugs); others must wait.

### 7.5 Suggested fixes

| Fix | Effort | Batch |
|---|---|---|
| **(You)** Answer the 23 queued decisions (any order) | — | — |
| Build a "Decisions Hub" page showing pending decisions with status | Low | v10.410 |
| Add a process: every review doc must propose a default + accept if Joshua silent for 3 batches | Medium | proposed for v10.385 review |

---

## Part 8 — Prioritization organ (pillar weights — rescue underway)

### 8.1 What this organ does

Tells the body what matters how much. Allocates the BSC composite-score budget across the four pillars (Financial / Customer Focus / Operational Excellence / People & Learning).

### 8.2 Current health (post-v10.384 rescue)

| Metric | Value |
|---|---|
| Canonical accessor live | ✓ (`utils/pillar_weights_canonical.py`) |
| Canonical weights | **0.68 / 0.14 / 0.06 / 0.12** (financial-heavy) |
| Orphan weights (org_config) | **0.40 / 0.25 / 0.25 / 0.10** (balanced) |
| Orphan-canonical match | **False** ⚠️ |
| Admin Bank Identity tab | ⚠️ deprecation notice live |
| KPI Library Pillar Weights tab | functional (writes canonical) |
| Shadow `pillars[].weight` field | **True** (still present) |
| History entries | 0 (will populate from future saves) |
| Validation | sum=1.0 + all positive + no dead organs |

### 8.3 Findings

**Finding P1 — SMOKING-GUN OBSERVED LIVE (v10.384).** Two pillar weight values currently in production state. Canonical 68/14/6/12 is what BSC engine uses. Orphan 40/25/25/10 was set by someone via Bank Identity admin tab — never applied. **Severity: MEDIUM** — body's prioritization has been silently inconsistent for an unknown duration.

**Finding P2 — Rescue underway (v10.384).** Canonical accessor module in place. Validation enforces constitution §12 (Flow Principle). Admin deprecation notice visible. History schema initialized. **Severity: NONE (in-progress)**.

**Finding P3 — Full consolidation requires 5 more batches.** v10.386 migrate KPI Library tab to use save_pillar_weights(); v10.387 add History view; v10.388 remove deprecated Bank Identity form; v10.389 remove shadow `pillars[].weight`; v10.390 remove org_config orphan. **Severity: LOW** — roadmap exists, work tractable.

**Finding P4 — Decision W5 pending.** Should canonical return to balanced 40/25/25/10 or stay 68/14/6/12 as deliberate crisis posture? **Severity: MEDIUM** — affects what 'truth' the body presents.

### 8.4 Diagnosis

The prioritization organ is **in transition**. The silent failure is now visible. The rescue is underway. Consolidation completes in 5 batches if the roadmap is followed.

### 8.5 Suggested fixes (committed in v10.384 doc)

Already documented in v10.384 roadmap. Continues v10.386-v10.390.

---

## Part 9 — Cross-organ interactions

### 9.1 The body works as one

Individual organ health is necessary but not sufficient. The interactions matter:

| Interaction | Pathway | Health |
|---|---|---|
| Skeleton → Nervous | Role assignment defines which KPIs flow to each staff | ✓ (after v10.391 Class B KPIs land) |
| Nervous → Circulatory | KPI actuals computed from CBS data flow through engines | ✓ (post-v10.379 write-bridge) |
| Recognition → Circulatory | Customer master feeds both profitability engines | ✓ (post-v10.383) |
| Recognition → UI | Customer master should feed Customer 360 page | ⚠️ (3,314 LOC unmigrated) |
| Prioritization → All | Pillar weights apply to every BSC computation | ⚠️ (mid-rescue) |
| Brain → All | Decisions drive what each organ does next | ⚠️ (23 queued) |
| Endocrine → All | Audit gates verify every organ's invariants | ✓ (270 gates) |

### 9.2 The key insight: silent failures travel between organs

The v10.383 silent failure illustrates this:
- Marketing intel had no `rm_code` (recognition organ data gap)
- RM profitability engine looked for `rm_code` there (nervous-system reading mismatch)
- Result: empty portfolios in every RM dashboard (UI consumed wrong-by-construction)

Any one organ's silent gap can propagate through several other organs before becoming visible.

### 9.3 The key strength: canonical engines isolate concerns

Post-Phase B, when the recognition organ gets fixed (v10.378 unified master with CBS), the circulatory organ (customer + RM profitability) automatically benefits. **One canonical truth, many consumers.** This is the architecture working as designed.

---

## Part 10 — Prioritized fix sequence

### 10.1 Tier-1 (next 6 batches — highest leverage)

These are the highest-leverage fixes. Each addresses a documented finding.

| Batch | Concern | Organ | Finding addressed | Cost |
|---|---|---|---|---|
| **v10.386** | Migrate KPI Library Pillar Weights tab to `save_pillar_weights()` | Prioritization | P3 | Medium |
| **v10.387** | Add History view to admin tab | Prioritization | P3 | Low |
| **v10.388** | Remove deprecated Bank Identity pillar weights form | Prioritization | P3 + N3 | Low |
| **v10.389** | Remove `pillars[].weight` shadow data | Prioritization | P3 | Low |
| **v10.390** | Implement Tier 1 Class B KPIs (NIM/CIR/ROE/NPS/DEP_GROWTH) | Nervous | N1 | Medium |
| **v10.391** | Implement Tier 2 Class B KPIs (DIGITAL_ACT + 5 LEGAL_*) | Nervous | N1 + N5 | Medium |

### 10.2 Tier-2 (next 6 batches — completing pillar work + structural fixes)

| Batch | Concern | Organ | Finding | Cost |
|---|---|---|---|---|
| v10.392 | Move `deadline\|*` cascade keys to `cascade_meta` | Nervous | N2 | Low |
| v10.393 | Normalize `active: null` → `active: false` | Nervous | N3 | Low |
| v10.394 | Deactivate or remove 133 unused KPI definitions | Nervous | N4 | Medium |
| v10.395 | Enumerate the 101 phantom roles | Skeleton | S1, S2 | Low |
| v10.396 | Add `role_status` field per v10.381 Decision 6 | Skeleton | S2 | Low |
| v10.397 | Add audit gate: org_hierarchy ≡ role_kpis on active roles | Skeleton | S3 | Low |

### 10.3 Tier-3 (Customer 360 migration — the longest workstream)

| Batch | Concern | Organ | Finding | Cost |
|---|---|---|---|---|
| v10.399 | Add preview "Canonical View" tab to Customer 360 (non-invasive) | Recognition | R1 | Medium |
| v10.400 | Migrate Tab 1 (Customer Lookup) | Recognition | R1 | Medium |
| v10.401 | Add Customer PBT panel | Recognition | C5 | Low |
| v10.402 | Migrate Tab 2 (Portfolio Intelligence) | Recognition | R1 | Medium |
| v10.403 | Migrate Tab 3 (Churn Risk) | Recognition | R1 | Medium |
| v10.404 | Migrate Tab 4 (NBA) | Recognition | R1 | Medium |
| v10.405 | Migrate Tab 5-7 (Segments, CLV, IFRS/IAS) | Recognition | R1 | Large |
| v10.406 | Add segment-conflict surfacing UI | Recognition | R4 | Low |

### 10.4 Tier-4 (cleanup + housekeeping)

| Batch | Concern | Organ | Finding | Cost |
|---|---|---|---|---|
| v10.398 | Consolidate dual customer-master caches | Circulatory | C3 | Low |
| v10.407 | Investigate pre-existing v10.319-v10.344 test failures | Endocrine | E5 | Medium |
| v10.408 | Formal gate-retirement process | Endocrine | E4 | Low |
| v10.409 | Categorize gates by organ for coverage report | Endocrine | E2 | Low |
| v10.410 | Build Decisions Hub page | Brain | B1 | Medium |

### 10.5 What this NOT a fix sequence for

- **Phase F (PostgreSQL migration)** — separate large effort not addressed by these tactical fixes
- **Performance optimization** — body is functionally correct; performance work is separate
- **New feature development** — diagnosis is about repair, not expansion
- **End-user UI redesign** — separate workstream

---

## Part 11 — Body-system framing

### 11.1 The body's overall state

The body is **alive, conscious of itself, and capable of self-repair**. Each organ has been characterized. Each drift has been catalogued. Each silent failure has been surfaced.

This is the difference between **a system you're flying blind on** and **a system you're flying with full instrumentation**. We now have instruments for all seven organs.

### 11.2 The body's strongest organs

1. **Endocrine** (audit gates) — 270 gates, 78 zero-drift batches
2. **Brain** (constitution + master prompt) — 29 consecutive lockstep batches
3. **Circulatory** (post-Phase B) — fully unified

### 11.3 The body's organs needing attention

1. **Recognition** (Customer 360 disconnection) — highest LOC at risk
2. **Nervous** (15 Class B orphans) — affects MD's complete banking story
3. **Prioritization** (mid-rescue) — 5 more batches to consolidation

### 11.4 The body's accumulated debt

| Debt category | Magnitude | Plan |
|---|---|---|
| Silent failures (known) | 2 documented; 1 fixed, 1 mid-rescue | v10.384-v10.390 |
| Unmigrated consumer pages | ~3,314 LOC in Customer 360 | Tier-3 (v10.399-v10.406) |
| Phantom roles | 101 | Tier-2 (v10.395-v10.397) |
| Unused KPI definitions | 133 of 185 | Tier-2 (v10.394) |
| Pre-existing test failures | ~5+ in older suites | Tier-4 (v10.407) |
| Queued decisions | 23 | Tier-1 prerequisite |

### 11.5 Total work remaining (rough estimate)

If all suggested fixes execute, ~24 batches end-to-end (v10.386 → v10.410). With autonomous batch continuation, that's tractable. Without it, you decide rate.

---

## Part 12 — What v10.385 deliberately does NOT do

Per Rule N2 (single concern), v10.385 explicitly:

- Does NOT modify any utility module
- Does NOT change any data file
- Does NOT add or remove any audit gate
- Does NOT decide any of the 23 queued Joshua decisions
- Does NOT execute any fix listed in Part 10
- Does NOT propose changes outside the existing roadmap

**Single concern: produce the comprehensive body-wide health survey.** Subsequent batches act on it under your approval.

---

## Part 13 — Honest acknowledgements

1. **The body has been substantively documented before.** v10.373 system review, v10.376 PMF review, v10.380 KPI review, v10.382 three reviews (Customer 360, KPI plan, pillar weights). v10.385 is the **synthesis** — pulls all those reviews into a single body-wide view. Some findings repeat; that's intentional (this is the consolidated view).

2. **Severity classifications are my judgment.** "MEDIUM" for an org-hierarchy phantom-roles issue might be HIGH to an operator who hits a confused cascade UI. You may reclassify.

3. **The fix sequence assumes batch-by-batch execution.** If we choose to bundle (e.g., do all pillar-weights consolidation in one larger batch), the sequence compresses but each batch grows. The current pattern of small batches is safer.

4. **23 queued decisions are real bottlenecks.** Without them answered, Tier-3 work (Customer 360 migration) has to make implementation choices without confirmation. We can proceed with defaults but you may want to weigh in first.

5. **Phase F (PostgreSQL) is a separate diagnosis.** This document is about the current state of the JSON-backed system. The constitution §4.3 PostgreSQL truth roadmap is acknowledged but not addressed here.

6. **The body's strongest finding is also its strongest method**: the discipline of constitution + audit gates + master-prompt lockstep + baseline diff + honest acknowledgements per batch. This is what produces 78 zero-drift consecutive batches. The methodology IS the architecture.

7. **The body has no critical/fatal conditions.** Every documented finding is tractable in ≤2 batches. No emergency triage needed.

8. **The Customer 360 migration is the biggest single workstream** in the fix sequence (Tier-3). It dominates batch count v10.399-v10.406. We could choose to defer it indefinitely; the rest of the body works fine without it migrating. But the value lock-in from canonical-everywhere is high.

9. **Performance is not addressed.** Page loads, query times, cache invalidation patterns — out of scope for a structural diagnosis. Worth a separate review if production complains.

10. **The 23 decisions could be drained in one sitting** if you allocated ~30-60 minutes to read the three v10.382 reviews + answer. That would unblock Tier-1+Tier-3 substantially.

11. **The body is self-aware of its own gaps now.** v10.385 codifies this self-awareness. Future batches don't have to re-discover; they execute.

12. **Body-system framing is genuinely useful — not just rhetorical.** Treating skeleton/circulatory/nervous/recognition/endocrine/brain/prioritization as organs forces us to ask: which organ does this concern? Are organs talking to each other correctly? This catches issues that a flat-file view doesn't.

13. **The diagnosis takes about 6KB of focus to read.** Each Part is a section. You don't have to read all at once. Skipping to Part 10 (prioritized fix sequence) is fine if you trust the diagnosis.

14. **My recommendations on order are negotiable.** v10.386 (KPI Library tab migration) is suggested first only because it's the natural continuation of v10.384. If Customer 360 work is higher priority, we can flip.

15. **This is v10.385. Phase B closes here.** v10.386+ is Phase C — execution against the diagnosis. The body has been comprehensively examined. Now it gets repaired.
