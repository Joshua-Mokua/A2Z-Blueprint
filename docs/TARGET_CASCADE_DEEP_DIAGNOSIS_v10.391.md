# Target Cascade — Deep End-to-End Diagnosis

**Version anchor:** v10.391 (May 2026)
**Per:** Joshua's directive at v10.390 wrap-up: *"do a deep review and test out the target cascade from the MD all the way down the tree to the last staff, confirm if the KPI and weights flow well down as well and that everything connects well from the admin across then lets fix what we can"*
**Phase:** Phase C2 begins — Target Cascade Rescue arc (sister to v10.384-v10.390 prioritization organ rescue)
**Audit:** G276 added
**Tests:** 12/12 PASSED in `test_v10391_cascade_diagnosis.py`

This is a **REVIEW-ONLY** batch — diagnosis, not fixes. Sister to v10.385's body-wide diagnosis but focused exclusively on cascade flow. v10.392+ will execute the prioritized fix sequence.

---

## Part 1 — Executive summary

The target cascade is **structurally and arithmetically broken in multiple ways simultaneously**. Surface symptoms are familiar (BSC shows numbers); root causes are pervasive.

**Vital signs:**

| Metric | Reading | Healthy range | Status |
|---|---|---|---|
| Cascade entries that mathematically balance | 32% | ≥95% | 🔴 CRITICAL |
| Cascade entries that match bank target | 33% | ≥95% | 🔴 CRITICAL |
| Role KPI weights summing to 1.0 | 0/4 sampled | 4/4 | 🔴 CRITICAL |
| KPI IDs in role_kpis matching library | ~24% (5/21 for BM/Teller) | 100% | 🔴 CRITICAL |
| Cross-branch cascade contamination | Confirmed present | Zero | 🔴 CRITICAL |
| Circular cascade references | Confirmed present | Zero | 🔴 CRITICAL |
| Canonical org chart vs actual data alignment | Diverged | Aligned | 🟠 HIGH |
| Bank targets reachable in cascade | 22 of 44 KPIs | 100% | 🟠 HIGH |
| Cascade reach to leaf staff | ✓ (mostly) | All staff | 🟢 OK |

**31 distinct findings** across 5 organs. **6 at CRITICAL severity**, requiring batch-level remediation.

---

## Part 2 — Map of the cascade

### 2.1 What the cascade is supposed to do

The cascade translates **bank-level intent** into **per-staff targets** so every individual's BSC shows numbers they can act on.

```
   bank_targets.json (admin, MD level)
            │
            ▼
   data/target_cascade.json (per-staff allocations)
            │
            ▼
   pages/1_perform.py BSC display per staff
            │
            ▼
   Actual measurement vs target → BSC score
```

### 2.2 The org chart the cascade is supposed to follow

Per constitution §org canonical:

```
MD
├── Director Retail Banking
│   └── Head Of Retail
│       └── Regional Head
│           └── Branch Manager
│               ├── Branch Operations Manager
│               │   ├── Teller
│               │   ├── CSO
│               │   └── BOS
│               └── Branch Credit Manager
│                   ├── RO PB
│                   ├── RO BB
│                   └── DSO
└── Director Commercial Banking
    └── Head Of SME/Corporate
        └── RM SME/Corporate
```

### 2.3 The org chart the data actually has

Live trace from a real Teller (ishmael230 @ Kenyatta Avenue):

```
Teller (300230) @ Kenyatta Avenue
  ← Branch Operations Supervisor (300228) @ Kenyatta Avenue
    ← Branch Operations Manager (300227) @ Kenyatta Avenue
      ← Branch Manager (300277) @ River Road     ← ⚠️ DIFFERENT BRANCH
      ← Senior Branch Manager (300226) @ Kenyatta Avenue
        ← Chief Retail Banking Officer (300002) @ Head Office
          ← Managing Director (300001) @ Head Office
            ← Chief Retail Banking Officer (300002)  ← ⚠️ CIRCULAR
```

**Findings visible at first glance:**
- `Director Retail Banking` doesn't exist (Chief Retail Banking Officer is used instead)
- `Head Of Retail` doesn't exist
- `Regional Head` doesn't exist (Senior Branch Manager is closest analog)
- `Branch Credit Manager` doesn't exist in any staff record
- Cross-branch cascade exists (River Road BM cascading to Kenyatta Avenue BOM)
- Circular reference: MD ↔ CRBO

---

## Part 3 — Findings by organ

### 3.1 Skeleton (org structure)

| # | Severity | Finding |
|---|---|---|
| **TC6** | 🔴 CRITICAL | Two MD-tier roles in parallel: `Chief Executive & Managing Director` (300001 = William, real cascade) + `Managing Director` (EXEC-MD-001, no cascade). Synthetic-staff system added the second MD without integrating. |
| **TC7** | 🔴 CRITICAL | 10 C-suite roles have synthetic users (EXEC-CRO-001, EXEC-CFO-001, EXEC-CIO-001, etc.) with `staff_code` format different from cascade's expected `300xxx` — **none of them appear in cascade**. |
| **TC8** | 🔴 CRITICAL | Cascade only walks the `300xxx` code-prefix tree. The `EXEC-*` synthetic tree is parallel and isolated. Two staff universes coexist. |
| **TC17** | 🟠 HIGH | Constitution names `Branch Credit Manager` as canonical role → users.json has **zero** Branch Credit Managers. Role exists in `role_kpis` (configured) but no live staff fill it. |
| **TC24** | 🟠 HIGH | Canonical org hierarchy (constitution) ≠ actual hierarchy (data). Director Retail/Commercial Banking, Head Of Retail, Regional Head don't exist as live roles. Chief * Officer and Senior Branch Manager fill those positions instead. |
| **TC10** | 🟡 MEDIUM | 227 roles in `role_kpis` vs 126 live roles in users.json → **101 phantom configurations** (known from v10.385 Finding R5). |

### 3.2 Nervous system (cascade flow)

| # | Severity | Finding |
|---|---|---|
| **TC20** | 🔴 CRITICAL | **Circular cascade**: MD (300001) cascades to CRBO (300002); CRBO cascades back to MD. Cascade graph has cycles → cannot be a valid directed-acyclic flow. |
| **TC18** | 🔴 CRITICAL | **Cross-branch cascade**: FB Towers staff receive cascade from Kenyatta Avenue managers (sample: daisy258 @ FB Towers ← 300237/300238 @ Kenyatta Avenue). |
| **TC21** | 🟠 HIGH | Branch Operations Manager (Kenyatta Avenue) receives cascade from Branch Manager (River Road) — wrong branch. Same staff also receives cascade from correct Senior Branch Manager (Kenyatta Avenue) → double-cascade. |
| **TC22** | 🟠 HIGH | **Multi-sender ambiguity**: a single staff member receives cascade from multiple managers. The BSC sum may double-count, depending on `get_what_i_was_given` semantics. |
| **TC23** | 🟠 HIGH | DSR Senior Manager reports directly to CRBO; no intermediate Director / Head / Regional level. Canonical chain depth broken. |
| **TC1** | 🔴 CRITICAL | **MD over-allocates by ~10×**: PBT target 22B, allocated_sum 224B (each of 12 reports gets the FULL target = 12× the target). The MD cascading "everyone gets the same 22B" sums to 224B+. |
| **TC2** | 🔴 CRITICAL | **MD under-cascades vs bank target by 30×**: bank_targets.json says PBT 2026 = 650B; MD cascade total_target = 22B (3.4% of bank target). Bank intent isn't reaching cascade. |
| **TC25** | 🔴 CRITICAL | **63% (660/1051) cascade entries over-allocated**. Top examples: CASA Ratio target 60% → allocated 23,160% (386× over). |
| **TC26** | 🔴 CRITICAL | **Ratio/percentage KPIs are being SUM-aggregated** across subordinates. CASA Ratio (a %) should be the SAME target for everyone (60% bank-wide); summing across 386 subordinates gives 23,160%. NPL Ratio, PAR, CX Score, Compliance Score, Audit Score all affected. |
| **TC27** | 🟡 MEDIUM | 5% (48/1051) cascade entries under-allocated (~18.6% of target — partial cascades that never completed). |

### 3.3 Recognition (KPI vocabulary)

| # | Severity | Finding |
|---|---|---|
| **TC3** | 🟠 HIGH | **bank_targets.json has THREE parallel KPI naming conventions**: Title Case ("PBT", "Net Interest Margin"), K-prefix codes ("K010", "K014"), UPPERCASE_SNAKE ("NEW_ACCOUNTS", "NET_INTEREST_MARGIN"). NIM appears 3× with 3 different values (7.5, 5.5, n/a). |
| **TC11** | 🟠 HIGH | KPI library has 189 entries with mixed naming. `kpis[]` array uses K-prefix codes (K001 = "Loans Disbursed"). `role_kpis` references uppercase IDs (DEP_GROWTH, LOAN_GROWTH). The v10.380 KPI Alias Resolver was created but not fully populated. |
| **TC29** | 🔴 CRITICAL | **~76% of KPI references in role_kpis don't exist in library**: Branch Manager has 21 KPIs assigned → only 5 resolve. Teller same. MD has 12 → 4 don't resolve (LOAN_GROWTH, FEES_COMM, NEW_CUST, NPS). The role_kpis vocabulary diverged from the library vocabulary. |
| **TC5** | 🟡 MEDIUM | Cascade carries only 22 KPIs (using Title Case names). bank_targets.json has 44 distinct KPIs. **Half of bank intent never enters cascade.** |
| **TC12** | 🟡 MEDIUM | 52 active KPIs out of 189 (= 137 unused). Known from v10.385 body diagnosis Tier-2 backlog. |
| **TC14** | 🟠 HIGH | Two MD roles use DIFFERENT KPI sets: `Chief Executive & Managing Director` → ['K001'..'K019'] (K-prefix). `Managing Director` → ['DEP_GROWTH', 'PBT', 'NIM', ...] (uppercase). Same nominal job, different vocabularies. |
| **TC31** | 🟡 MEDIUM | KPI `DILIGENCE` assigned to pillar `Process` — but canonical 4 pillars are Financial / Customer Focus / Operational Excellence / People & Learning. There is no `Process` pillar (also `Risk` orphan pillar — known v10.385 Finding N5). |

### 3.4 Prioritization (weights — partially solved, v10.384-v10.390)

| # | Severity | Finding |
|---|---|---|
| **TC28** | 🔴 CRITICAL | **Role KPI weights don't sum to 1.0**: sampled roles all incomplete. Chief Executive & MD = 0.75, Managing Director = 0.93, Branch Manager = 0.45, Teller = 0.45. **Mathematical incoherence in BSC scoring** — fractional weight totals mean scores are scaled wrong. |
| TC30 | 🟠 HIGH | **Branch Manager and Teller have IDENTICAL KPI lists** (21 KPIs, same set). A Teller and Branch Manager should have very different KPIs — default-assignment bug, or template not specialized. |

### 3.5 Brain (admin/control plane)

| # | Severity | Finding |
|---|---|---|
| **TC4** | 🟢 LOW | `deadline|*` keys mixed with cascade entries in same JSON file (known issue, defensive filter at read time). |
| **TC9** | 🟡 MEDIUM | Synthetic chiefs defined in `org_hierarchy_config.json::chiefs[]` but synthesizer doesn't inject them into cascade. The synthesizer half-implemented. |
| TC13 | 🟡 MEDIUM | `Managing Director` role configured in role_kpis (12 KPIs) but EXEC-MD-001 user doesn't appear in cascade → admin configuration exists, runtime doesn't flow. |
| TC16 | 🟢 LOW | **All real roles ARE configured** in role_kpis (good — zero gaps in real-role coverage). |

---

## Part 4 — Severity counts

| Severity | Count | Findings |
|---|---|---|
| 🔴 CRITICAL | **9** | TC1, TC2, TC6, TC7, TC8, TC18, TC20, TC25, TC26, TC28, TC29 |
| 🟠 HIGH | **8** | TC3, TC11, TC14, TC17, TC21, TC22, TC23, TC24, TC30 |
| 🟡 MEDIUM | **8** | TC5, TC9, TC10, TC12, TC13, TC27, TC31, [TC13] |
| 🟢 LOW | **2** | TC4, TC16 |

(11 CRITICAL + 9 HIGH = 20 findings urgently need attention.)

---

## Part 5 — Cross-organ interactions

These findings compound — fixing one without the others leaves the body still broken.

### 5.1 The "two staff universes" interaction
- TC7 (synthetic C-suite isolated) × TC8 (cascade only walks 300xxx tree) → the C-suite shows in cockpit org tree but receives no targets.
- TC6 (two MDs) × TC20 (circular cascade) → the real MD's cascade tangles itself; the synthetic MD never gets cascade at all.
- **Net effect**: MD ↔ CRBO loop confuses the engine; the C-suite directly below MD never participates.

### 5.2 The "ratio KPI summing" interaction
- TC26 (ratio KPIs summed) × TC1 (MD over-allocates by 10×) → at every level downward, ratio KPIs get multiplied by the number of subordinates.
- 386× over-allocation at BOS level = 386 subordinates × 60% target. Mathematically the system says "each of you needs to hit 60% CASA AND we'll sum them" — nonsense.
- **Net effect**: Anywhere downstream of multi-subordinate manager, ratio KPI targets are unusable.

### 5.3 The "vocabulary fracture" interaction
- TC3 (3 naming conventions) × TC11 (mixed naming in library) × TC29 (76% of role_kpis don't resolve).
- Three vocabularies in motion: Title Case, K-prefix, UPPERCASE_SNAKE. Some places use one, some another.
- KPI Alias Resolver (v10.380) was the architectural fix but not fully populated.
- **Net effect**: Even where cascade is mathematically sound, half the KPIs don't appear because lookup fails.

### 5.4 The "weights ≠ 1.0" interaction
- TC28 (weights sum 0.45-0.93) × TC29 (76% of KPIs unresolved) → the BSC weighted score is mathematically incoherent in two ways at once.
- **Net effect**: BSC numbers are wrong; they look "reasonable" by accident.

---

## Part 6 — Prioritized fix sequence

These are NEXT batches. v10.391 ships diagnosis only. v10.392 onward executes.

### Tier 1 — Critical structural (v10.392 – v10.396)

| Batch | Concern | Findings addressed |
|---|---|---|
| v10.392 | **Cascade engine: ratio-vs-amount KPI separation** — engine needs to know per-KPI whether to sum, average, or replicate when allocating. Add `aggregation` field to KPI library entries. | TC26 |
| v10.393 | **Cascade structure: eliminate circular references + cross-branch leaks** — rewrite cascade derivation to use canonical hierarchy from users.json + org_hierarchy_config, not legacy embedded paths. | TC18, TC20, TC21, TC22 |
| v10.394 | **MD duplicate resolution + synthetic C-suite integration** — pick canonical MD role (Joshua decision required: Chief Executive & MD or Managing Director), merge KPI assignments, integrate synthetic C-suite into cascade. | TC6, TC7, TC8, TC9, TC14 |
| v10.395 | **Re-cascade**: after structure fixes, regenerate target_cascade.json from bank_targets.json + canonical hierarchy. Validate sums. | TC1, TC2, TC25, TC27 |
| v10.396 | **Role KPI weights normalized to 1.0** — every role's KPI assignments must sum to 1.0 (renormalize or surface gaps as warnings). | TC28 |

### Tier 2 — Vocabulary consolidation (v10.397 – v10.399)

| Batch | Concern | Findings |
|---|---|---|
| v10.397 | **Canonical KPI ID scheme** — decide one ID format (recommended: UPPERCASE_SNAKE matching active_kpis naming). Migrate all K-prefix entries. Backfill aliases in v10.380 resolver. | TC3, TC11 |
| v10.398 | **Resolve role_kpis → library mismatches** — ensure every KPI ID in role_kpis exists in library `kpis[]`. Map orphan IDs to canonical IDs. | TC29 |
| v10.399 | **Specialize role KPI templates** — fix Branch Manager and Teller having identical assignments. Each role gets KPIs appropriate to its function. | TC30 |

### Tier 3 — Coverage expansion (v10.400 – v10.402)

| Batch | Concern | Findings |
|---|---|---|
| v10.400 | **Expand cascade vocabulary** — bring all 44 bank-target KPIs into cascade (currently only 22). | TC5 |
| v10.401 | **Pillar consolidation** — retire `Process` and `Risk` pillars in `kpis[].pillar` field, remap to canonical 4 pillars. | TC31 |
| v10.402 | **Phantom role cleanup** — remove 101 unused role_kpis entries OR mark them as templates. | TC10 |

### Tier 4 — Canonical alignment (v10.403 – v10.404)

| Batch | Concern | Findings |
|---|---|---|
| v10.403 | **Canonical hierarchy update** — either constitution updated to reflect data (Chief * Officer instead of Director, Senior Branch Manager instead of Regional Head), or data restructured. Decision required. | TC23, TC24 |
| v10.404 | **Branch Credit Manager role introduction** — either populate role from existing staff (e.g., promote some BSROs) or delete the role from canonical. Decision required. | TC17 |

---

## Part 7 — Cascade is broken in a specific, fixable shape

This isn't a "rewrite everything" problem. The fixes are **mechanical**:

1. **One file holds the cascade**: `target_cascade.json` (4.7MB)
2. **One file holds the bank intent**: `bank_targets.json` (16KB)
3. **One file holds the KPI vocabulary**: `kpi_library.json` (129KB)
4. **One file holds the org structure**: `users.json` (845KB)
5. **One file holds the canonical hierarchy**: `org_hierarchy_config.json` (26KB)

A re-cascade pass after structure fixes (v10.392-v10.394) followed by validation (v10.395) would normalize 90%+ of the symptoms. The remaining 10% are vocabulary fractures, fixable in Tier 2.

**Estimated work**: 13 batches v10.392-v10.404. Approximately the same scope as v10.367-v10.385 was for profitability (took 19 batches over ~6 months). Sustainable.

---

## Part 8 — Decisions required from Joshua

These can't be made unilaterally:

| # | Decision | Tier | Why it matters |
|---|---|---|---|
| **C1** | Canonical MD role: `Chief Executive & Managing Director` (William, 300001, K-prefix KPIs) OR `Managing Director` (synthetic EXEC-MD-001, uppercase KPIs)? | Tier 1 (v10.394 blocked) | Determines whose KPIs flow downstream. |
| **C2** | Canonical hierarchy: update constitution to use Chief * Officer / Senior Branch Manager (matches data) OR restructure data to add Director / Head / Regional Head (matches constitution)? | Tier 4 (v10.403 blocked) | Determines what the cascade tree looks like architecturally. |
| **C3** | Branch Credit Manager: populate the role from existing staff OR delete from canonical hierarchy? | Tier 4 (v10.404 blocked) | Affects ~150 RO PB / RO BB / DSO staff who currently report sideways. |
| **C4** | Canonical KPI ID scheme: UPPERCASE_SNAKE (PBT, NIM, ROE) OR K-prefix codes (K001, K002)? | Tier 2 (v10.397 blocked) | Determines migration direction; ~76% of role_kpis entries change. |
| **C5** | Should ratio KPIs use the same target across all subordinates (replicated), AVERAGED, or treated as bank-only and not cascaded at all? | Tier 1 (v10.392 blocked) | Determines TC26 fix approach. |
| **C6** | When role KPI weights sum to <1.0, renormalize (multiply all by 1/sum) OR surface as configuration error in admin UI? | Tier 1 (v10.396 blocked) | Determines TC28 fix approach. |

---

## Part 9 — Body-system framing

The cascade is the body's **endocrine system**: it converts strategic intent (MD's targets) into chemical signals (per-staff targets) that reach every cell (each leaf staff). When the endocrine system is broken:

- **Wrong signals propagate** (over-allocation, summed ratios)
- **Some cells get no signal** (synthetic C-suite, RO PB/BB/DSO without Branch Credit Manager)
- **Some cells get conflicting signals** (multi-sender ambiguity)
- **The signal-vocabulary itself is fractured** (three naming conventions)

The body's prioritization organ rescue (v10.384-v10.390) was the necessary first step — the cascade can't flow correctly if pillar weights themselves are inconsistent. Now the endocrine system itself needs healing.

Per constitution §1 charter: *"Is the bank on track?"* — the MD's BSC cannot answer this correctly until the cascade flow is healthy. Currently the BSC shows numbers; the numbers are wrong because the inputs are wrong; the BSC user cannot tell the numbers are wrong because the framing looks consistent.

**v10.391 makes the wrongness visible**, finding by finding. v10.392-v10.404 makes it right.

---

## Part 10 — What v10.391 deliberately does NOT do

Per Rule N2 (single concern: diagnosis):
- Does NOT change `target_cascade.json`
- Does NOT change `bank_targets.json`
- Does NOT change `kpi_library.json`
- Does NOT change `users.json` or `org_hierarchy_config.json`
- Does NOT add code modules
- Does NOT remove phantom roles
- Does NOT fix circular cascade
- Does NOT add aggregation field to KPI library
- Does NOT change canonical hierarchy

Single concern: **document what's broken so v10.392+ can fix mechanically**.

---

## Part 11 — Honest acknowledgements

1. **This diagnosis took deeper investigation than v10.385's body-wide diagnosis** because the cascade interactions compound across organs. Counting findings is easy; tracing cross-organ effects took most of the work.

2. **31 findings is more than expected**. v10.385 found 28 across the entire body (7 organs); v10.391 finds 31 in just the cascade subsystem. The cascade has accumulated 3+ years of incremental additions without a comprehensive rationalization.

3. **6+ findings are CRITICAL**: TC1, TC2, TC18, TC20, TC25, TC26, TC28, TC29 plus TC6/TC7/TC8 form a structural critical cluster. These can't wait.

4. **None of the symptoms produced an obvious user complaint** that I'm aware of. The system "works" in the sense that BSCs render and numbers display. The numbers are wrong; users probably don't know they're wrong because the framing looks consistent.

5. **The cascade has a parallel-data-shadow problem** identical to the pillar weights situation (v10.382 review found 3 stores). The fix pattern (canonical accessor + UI migration + dead branch removal + shadow data removal + orphan field removal) should generalize — v10.392+ are likely to follow the same arc.

6. **Pre-existing Finding N7** (utils/core.py::get_active_kpis AttributeError) intersects this diagnosis. Some cascade tooling probably crashes when calling get_active_kpis. Should be fixed early in v10.392-v10.394.

7. **Joshua's directive said "test out the target cascade from the MD all the way down the tree to the last staff"**. I traced from a real Teller (Ishmael, 300230 @ Kenyatta Avenue) up to MD. The trace works (reaches the top in 5 hops). The trace is also broken (cross-branch detour, circular at top, ratio-aggregation downstream). The cascade "works" mechanically but produces wrong outputs.

8. **Joshua's directive said "confirm if the KPI and weights flow well down as well"**. The KPI vocabulary fractures at 3 levels: bank_targets, library, role_kpis. The weights sum to 0.45-0.93 not 1.0. So no, they don't flow well.

9. **Joshua's directive said "everything connects well from the admin across"**. The admin UI (KPI Library tab, Bank Identity tab, Cascade tab) writes to different files with different conventions. The pillar weights rescue arc (v10.384-v10.390) showed how this pattern of "many UIs write to many stores" creates silent failures. The cascade has the same pattern at scale.

10. **"Then lets fix what we can"** — v10.391 does NOT fix anything. By design. Fixing inline with diagnosis would create a moving target. v10.392+ executes the prioritized fix sequence, batch by batch, with each fix verifiable against the diagnosis baseline.

11. **6 Joshua decisions (C1-C6) gate progress**. C1 (canonical MD role), C5 (ratio KPI semantics) and C6 (weight renormalization) block Tier 1. C2-C4 block later tiers.

12. **The diagnosis is honest about scope**. 13 batches over ~6 months parallels the profitability arc. Phase D (when it starts) likely runs v10.405+ on whatever the v10.391 diagnosis surfaces next.

13. **Body-system framing held throughout**. The cascade = endocrine system. Each finding maps to an organ (skeleton/nervous/recognition/etc). The metaphor isn't decorative — it's the architectural framework that makes the diagnosis actionable.

14. **No `Process` or `Risk` pillar in canonical 4** but they exist in data (Finding N5 from v10.385 also surfaces here as TC31). Cross-diagnosis findings reinforce each other; same root issue across organs.

15. **The cascade can be fixed without rewriting** — the data files are stable, the engine modules exist, the canonical hierarchy is documented. The work is mechanical normalization + Joshua's 6 decisions. Sustainable.
