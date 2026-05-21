# A2Z MIS 360 — Governance Constitution (Internal Codification)

**Version anchor:** v10.377 (May 2026)
**Source:** Joshua's official Technical Governance Framework (transmitted at v10.376 wrap-up)
**Purpose:** Internal codification of the constitutional mandates that govern all future development. Maps current state to target state. Defines the migration arc. **All future batches reference this document.**

Companion to:
- `docs/SYSTEM_STATE_REVIEW_v10.373.md` (system-wide mapping)
- `docs/PERFORMANCE_MANAGEMENT_FRAMEWORK_REVIEW_v10.376.md` (PM ecosystem)
- This document: the constitutional anchor

---

## Part 1 — The constitutional mandates that change how we build

### 1.1 Architectural mandates (Sections 4-9 of the Framework)

| Mandate | Constitutional reference | Status today | Target |
|---|---|---|---|
| **PostgreSQL = single source of truth** | §4.3, §5 | JSON-based (208 data files) | Phase F migration |
| **Universal BSC data contract** `(staff_code, kpi_id, value, period, source_module)` | §5.1 | `bsc_engine.submit()` enforces it for direct submissions; canonical engines bypass | **v10.377 contract layer + unifier** |
| **Central BSC Integration Engine** | §5.2 | `bsc_engine.py` exists with submit/get_actual/submit_batch | Wire canonical engines through it (v10.378+) |
| **Data flow: Source → Staging → Transformation → Clean → BSC → Reporting** | §5.3 | Canonical engines: CBS → engine → output (skipping BSC integration step) | v10.377 + v10.378 add the BSC integration step |
| **Staging tables for source data** | §7.2 | We have `cbs_baseline.json` etc. but not formal staging | PostgreSQL migration |
| **Audit logs for every critical action** | §8.1, §8.2 | We have G128 baseline, gates G249-G262, in-code audit | PostgreSQL audit tables (Phase F) |
| **Layered architecture: Frontend / Backend API / Business Logic / Database / Integration / Audit** | §4.1 | Streamlit pages + utils modules; no formal FastAPI yet | Phase F |
| **Streamlit = internal; React = enterprise/executive** | §9.1 | Pure Streamlit (123 pages) | Phase E |
| **RBAC** | §10.1 | `pages/_access.py::require_access()` enforces by scope; piggyback pattern | Already aligned (read-only) |

### 1.2 Process mandates (Sections 11-14 of the Framework)

| Mandate | Constitutional reference | How we apply it |
|---|---|---|
| **No random builds** | §11.1 | Rule N2 (single concern per batch) + audit gate before/after (Rule N3) — already aligned |
| **Architecture change control** | §11.2 | Master prompt lockstep (every batch syncs); 21 consecutive batches at v10.376 — already aligned |
| **Technical debt documented** | §11.3 | Honest acknowledgements in every CHANGELOG (Rule N4) — already aligned |
| **Deployment governance** | §11.4 | G128 baseline + verifier 328/328 + clean-extract smoke test per batch — already aligned |
| **Flow Principle** | §12 | Every batch threads back to the MD's daily question — already aligned via canonical engines |
| **Continuous improvement** | §13 | Continuous improvement principle (Rule N8 KAIZEN) — already aligned |
| **Final governance** | §14 | Body-system framing (organs in harmony) — already aligned |

### 1.3 What changes in batch behavior from v10.377 onwards

1. **Every new canonical engine MUST produce records conforming to the Universal BSC Data Contract.** Format: `UniversalBSCRecord(staff_code, kpi_id, value, period, source_module, [metadata])`. Output of the engine → input of contract validator → eventually bridged to BSC actuals.

2. **No new JSON storage** for performance data. Existing JSON files (kpi_library.json, target_cascade.json, bsc_actuals_*.json) are tolerated during the migration arc but no NEW JSON storage gets added for performance/KPI data. (Configuration JSON like role taxonomy is fine; performance JSON is not.)

3. **Every canonical engine ships with a BSC bridge** as part of its scope. v10.376 established this for PBT (read-only). All future canonical engines (Phase D, ~108 KPIs) ship a bridge as part of their batch — not as a separate later concern.

4. **`source_module` field is mandatory and informative.** Acceptable values follow a naming convention: `canonical_<dimension>_engine_v<batch>` (e.g. `canonical_pbt_staff_engine_v10377`). When migration removes old paths, these source_module names are how we trace which engine produced each record.

5. **Migration arc is explicit, not implicit.** PostgreSQL migration is Phase F. Until then, the JSON layer is the implementation; the contract layer (v10.377+) is the public interface. When PostgreSQL arrives, contract callers don't change — only the storage layer.

---

## Part 2 — The five problems A2Z MIS 360 solves (per Joshua's strategic restatement)

The constitution is the HOW. These are the WHY:

### Problem A — Multiple integrating systems → reporting crisis

> "Picture a scenario where every mobile app we had needed a phone to operate and imagine how many phones we will be walking around with."

Today's banks have many peripheral systems (Excel, BI tools, custom reports, dashboards) each integrating to core banking. They don't talk to each other. Reports disagree.

**A2Z MIS 360 = the phone that houses all the apps.** Single platform, every module best-in-class, all sharing the BSC data contract. Systems-thinking framing (Donella Meadows): the whole is more than the sum of the parts.

### Problem B — Lack of trustworthy management intelligence

Aggregating data from peripheral systems for trustworthy decision-support. Today: each system has its own truth.

**A2Z MIS 360 = single MIS aggregating + presenting intelligence.** The 109-active-KPI BSC framework with cascade is the answer.

### Problem C — Staff performance not measured objectively

Most banks rely on quarterly subjective appraisals. No daily/instant productivity measurement across all staff.

**A2Z MIS 360 = daily productivity measurement for every staff in every department.** The role taxonomy (v10.374) classifies every role; the BSC engine measures every staff against their KPIs daily. The virtual bank (v10.358+) is the testbed proving every role can be simulated and measured.

### Problem D — Target cascade is a nightmare

Cascading targets from MD to last staff takes time, misaligns, distorts. Today's banks struggle.

**A2Z MIS 360 = MD sets a target → it flows smoothly to the last individual + cascade is tracked.** Target cascade engine + v10.371 multi-level schema + G258 hierarchy identity already deliver this for PBT. Phase D extends to all 109 active KPIs.

### Problem E — Strategy formulation without solid MIS foundation

Banks formulate strategies without clear performance picture or true SWOT. Strategies don't match customer/bank/market needs.

**A2Z MIS 360 = strategy anchored in real-time MIS.** Strategic Initiatives module + Board Papers + Benchmarking + Performance Insights all consume the canonical layer.

---

## Part 3 — The body-system framing, anchored in the constitution

| Body system | Banking analog | Constitutional alignment |
|---|---|---|
| **Skeleton** (seniority) | Role hierarchy: MD → Chiefs → Heads → Managers → Officers → Junior | §4.1 layered architecture; §10 hierarchy-based RBAC |
| **Circulatory** (profitability) | PBT flow: per-customer atomic → staff → branch → SBU → bank | §5.5 reconciliation; v10.368-v10.372 canonical engines |
| **Nervous** (KPI flow) | Universal contract carrying signals from all modules to BSC | §5.1 universal data contract; **v10.377 establishes this** |
| **Endocrine** (control loops) | Audit + feedback signals throughout | §8 audit & traceability; existing G1-G262 gates |
| **Brain** (governance) | Constitution + architectural decisions | This document |

The constitution makes the body-system framing not just metaphor but structural. The nervous system (universal data contract) is what v10.377 establishes — the signal carrier that makes all organs work in harmony.

---

## Part 4 — Today's specific directive ("conduct all tests we need to ascertain the system works when rolled into production")

> "Our major action on this chat is towards what we are doing to have a virtual bank that will help us conduct all tests we need to ascertain that the system is going to work when we roll it into production... Let's have our virtual bank unify how all KPIs flow, test all modules and ensure every staff works and is measured."

This shapes v10.377's deliverables:

1. **Universal BSC Data Contract** (`utils/bsc_universal_contract.py`) — the schema + validator. Every canonical engine output goes through this filter.

2. **Virtual Bank KPI Unifier** (`utils/virtual_bank_kpi_unifier.py`) — runs the full virtual bank → canonical engines → universal records pipeline. Demonstrates that the seeded bank can produce production-shape KPI records for the BSC.

3. **Every staff produces measurable records.** The unifier walks the staff dimension (compute_pbt_by_staff returns all tagged staff) and produces one PBT record per staff. For now: PBT. Phase D extends to all 109 active KPIs per role.

4. **Test that records validate.** Every record produced must pass `validate_universal_record()`. The integration test will assert this for the full seeded bank output.

5. **Read-only still** — the records are produced for inspection/testing, not yet submitted to bsc_actuals. The write-bridge is v10.378+ when consumer mapping is complete.

---

## Part 5 — What v10.377 deliberately does NOT do

To preserve Rule N2 (single concern):

- Does NOT migrate JSON to PostgreSQL (Phase F)
- Does NOT write to `bsc_actuals_*.json` via `bsc_engine.submit()` (deferred to v10.378+ after consumer mapping)
- Does NOT merge customer master (deferred to v10.378)
- Does NOT refactor `customer_profitability.py` / `rm_profitability.py` (deferred to v10.379+)
- Does NOT touch the BSC engine itself (no changes to `bsc_engine.py`, `bsc_score_computation.py`, `cascade_hierarchy.py`)
- Does NOT add new KPIs (the 109 active stay as defined)
- Does NOT change pillar weights, KPI IDs, or any structural data
- Does NOT introduce FastAPI or React (Phase E)

Single concern: **establish the Universal BSC Data Contract layer and demonstrate the virtual bank produces conforming records for every tagged staff.**

---

## Part 6 — The next 10 batches, constitutionally aligned

| Batch | Concern | Constitutional alignment |
|---|---|---|
| **v10.377 (this)** | Universal Data Contract + Virtual Bank KPI Unifier | §5.1 contract; §5.2 central integration prep |
| v10.378 | Customer master merge | §5.5 reconciliation (atomic per-customer record) |
| v10.379 | Write-bridge: canonical PBT → bsc_actuals via bsc_engine.submit | §5.2 central integration engine becomes mandatory |
| v10.380 | KPI-ID canonicalisation (fix kpi_library vs role_kpis drift) | §5.4 validation; §6.3 module consistency |
| v10.381 | Refactor customer_profitability.py to canonical | §6.3 consistency |
| v10.382 | Refactor rm_profitability.py to canonical | §6.3 consistency |
| v10.383 | Phase C: branch field staff actions (CSO, BOS, RM PB/BB, DSO) | §12 flow principle |
| v10.384 | Phase C: branch management actions | §12 flow principle |
| v10.385 | Phase C: HO sales actions | §12 flow principle |
| v10.386 | Phase C: regional/division leadership | §12 flow principle |

---

## Part 7 — Migration arc to PostgreSQL (Phase F, when we get there)

Acknowledging the constitutional mandate while not yet executing:

1. **Schema definition** — design PostgreSQL tables matching the universal contract: `performance.actuals(staff_code, kpi_id, value, period, source_module, submitted_at, actor, metadata)`. Mirror existing bsc_actuals_*.json schema for backward compat.

2. **Staging tables** — `staging.cbs_accounts`, `staging.cbs_customers`, etc. Today's CBS CSV writes become Postgres COPY operations.

3. **Reconciliation tables** — `audit.reconciliation_log` records every Σ identity check (G256/G257/G258 etc.) with timestamp + outcome.

4. **Migration path** — JSON file content migrates into Postgres while file writes are mirrored. Once consumers are migrated to read from Postgres, JSON writes stop.

5. **API layer** — FastAPI endpoints expose canonical engines. Streamlit pages call APIs instead of importing utils directly. (Phase E + F overlap.)

This is the destination; v10.377 establishes the contract layer that makes the migration tractable.

---

## Part 8 — Honest acknowledgement

The constitution makes explicit what was previously implicit: the system's goal is enterprise-grade banking MIS, not just profitability reconciliation. PBT was the prototype that proved the unification pattern works. v10.377 establishes the data-contract layer that makes the pattern apply to all KPIs and all modules. Phase D extends; Phase F migrates to Postgres; Phase E adds React frontend.

The body-system framing remains intact: skeleton (seniority) + circulatory (profitability done) + nervous (KPI flow established v10.377) + endocrine (audit) + brain (constitution). All organs working in harmony, as Joshua requires.

The mantra holds: **"all the system and organs all functioning perfectly and in harmony to make the one body as a whole."**
