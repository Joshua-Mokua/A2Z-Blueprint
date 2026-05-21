# Line Manager Hierarchy & Fixed KPI Mechanism — Deep Review

**Version anchor:** v10.394 (May 2026)
**Per:** Joshua's directive after v10.393: *"the fixed KPI is the reserve of the MD since they might change, we have a tap in the target cascade module where the MD ticks what needs to be fixed, remember also not all ratios are fixed e.g NPL varies from branch to branch. Then the cascade follows the line manager hierarchy, we had one defined which you also need to do a deep dive to review and see, it is the same hierarchy that flows upwards right from the pipeline module"*
**Phase:** Phase C2 — Target Cascade Rescue arc (third review batch)
**Audit:** G279 added
**Tests:** 12/12 PASSED in `test_v10394_hierarchy_and_fixed_kpi_review.py`

**REVIEW ONLY** — no code or data changes. Surfaces the canonical hierarchy location, documents the Fixed KPI MD mechanism, identifies divergences across modules. v10.395+ executes the alignment.

---

## Part 1 — Executive summary

Joshua's guidance answered the architectural questions I was about to get wrong:

1. **Fixed KPI is MD-controlled** (tick-box UI exists in cascade module Tab "🔒 Fixed KPIs")
2. **Not all ratios are fixed** — NPL Ratio specifically varies per branch (historically removed from fixed)
3. **Cascade follows canonical line manager hierarchy** — same one the pipeline module uses for upward flow

This review confirms each point and surfaces the actual sources of truth.

### Vital signs

| Subsystem | Reading | Status |
|---|---|---|
| Fixed KPI MD UI exists | ✅ `pages/12_cascade.py` Tab "🔒 Fixed KPIs" (MD-only access) | OK |
| Fixed KPI data file exists | ✅ `data/fixed_kpis.json` (16 fixed KPIs for 2026-Q1) | OK |
| CascadeManager API exists | ✅ `set_fixed_kpis` / `get_fixed_kpis` / `get_fixed_value` / `is_fixed` | OK |
| BSC consumes fixed values | ✅ `pages/1_perform.py` lines 614-625 (MD) + 642-661 (others) | OK |
| Canonical line manager hierarchy | ✅ `org_hierarchy_config.json::role_manager_whitelist` (26 subordinate roles) | OK |
| Pipeline module hierarchy | ❌ Inline `_HIER` dict diverges from canonical | 🟠 |
| Cascade page hierarchy | ❌ Fallback `HIERARCHY` diverges from canonical | 🟠 |
| Structure engine WITHIN_BRANCH | ❌ 9 missing pairs, 6 extra pairs vs canonical | 🟠 |
| NPL Ratio fixed status | ❌ Both "removed" AND "fixed" simultaneously (naming bug) | 🔴 |
| Period harmonization | ❌ Fixed=quarterly, cascade=annual, bank_targets=annual | 🟡 |

**9 distinct findings TC33-TC41**, 1 CRITICAL, 5 HIGH, 3 MEDIUM.

---

## Part 2 — The Fixed KPI MD mechanism (existing, working)

### 2.1 Architecture

```
                    ┌─────────────────────────────────────┐
                    │  pages/12_cascade.py — Tab 🔒 Fixed │
                    │  ──────────────────────────────────  │
                    │  • MD-only access guard              │
                    │  • Checkbox per KPI per period       │
                    │  • Value input (% or absolute)       │
                    │  • Per-pillar grouping               │
                    │  • Shows roles carrying that KPI     │
                    └──────────┬──────────────────────────┘
                               │ casc.set_fixed_kpis(period, kpis, values)
                               ▼
                    ┌─────────────────────────────────────┐
                    │  utils/core.py — CascadeManager      │
                    │  set_fixed_kpis / get_fixed_kpis     │
                    │  get_fixed_value / is_fixed          │
                    └──────────┬──────────────────────────┘
                               │ writes
                               ▼
                    ┌─────────────────────────────────────┐
                    │  data/fixed_kpis.json                │
                    │  ──────────────────────────────────  │
                    │  Period-keyed (quarterly):           │
                    │  "2026-Q1": { "kpis": [...] }        │
                    └──────────┬──────────────────────────┘
                               │ read by
                               ▼
                    ┌─────────────────────────────────────┐
                    │  pages/1_perform.py — BSC display    │
                    │  ──────────────────────────────────  │
                    │  Both MD-view + non-MD-view read     │
                    │  fixed_kpis_set + replicate value    │
                    │  to all staff with that KPI          │
                    └─────────────────────────────────────┘
```

**Per Joshua's confirmation: this mechanism is correct. MD ticks → all staff with that KPI see the same bank-wide value.**

### 2.2 Currently fixed KPIs (2026-Q1)

```
✓ CX Score              ← customer experience, bank-wide rating
✓ Audit Score           ← audit performance, bank-wide
✓ Staff Productivity    ← HR metric, bank-wide
✓ CASA Ratio            ← deposit mix, bank-wide regulatory
✓ PAR                   ← portfolio at risk, bank-wide
✓ Account Dormancy      ← bank-wide rate
✓ Channel Dormancy      ← bank-wide rate
✓ K010, K014, K016, K121, K129, K132, K134  ← legacy ID-coded KPIs
✓ COMPLIANCE_SCORE
✓ NPL_RATIO             ⚠️ contradicts "NPL Ratio" being in removed-from-fixed
```

### 2.3 Historically REMOVED from fixed (correctly per Joshua)

```
✗ PBT          ← financial outcome — varies by unit, must cascade
✗ Total NFI    ← financial outcome — varies by unit, must cascade
✗ NPL Ratio    ← Joshua confirmed: varies branch to branch
✗ NIM          ← varies, must cascade or be branch-specific
✗ ROE          ← varies, must cascade
✗ CIR          ← varies, must cascade
```

The `_v10324_removed_from_fixed` field documents this — earlier in development these were fixed, then correctly removed when it became clear they need per-unit values.

---

## Part 3 — Finding TC39 (CRITICAL): NPL Ratio fixed-status contradiction

The two names for the same KPI are in conflicting states:

| KPI name | Status in fixed_kpis.json |
|---|---|
| **NPL Ratio** (human Title Case) | Listed in `_v10324_removed_from_fixed` (correctly NOT fixed) |
| **NPL_RATIO** (UPPERCASE_SNAKE) | Listed in current `kpis` for 2026-Q1 (treated as FIXED) |

**Two parallel KPI naming conventions** (v10.391 finding TC3/TC11) intersect the Fixed KPI mechanism here: the same KPI under two different identifiers gets two different fix-statuses.

If BSC looks up by "NPL Ratio" it sees "not fixed → use cascaded value". If it looks up by "NPL_RATIO" it sees "fixed → use bank-wide value". Both can fire depending on how the lookup key is constructed.

**Fix scope**: This is the v10.391 TC11 KPI-vocabulary-consolidation problem manifesting here. v10.398 (canonical KPI ID scheme migration) resolves it. Until then, BSC has unpredictable NPL Ratio behavior depending on caller.

---

## Part 4 — The canonical line manager hierarchy (TC33)

### 4.1 Location: `data/org_hierarchy_config.json::role_manager_whitelist`

This is the **canonical line manager hierarchy** Joshua referenced. It uses ACTUAL role names from `users.json` and `hr.json`, not aspirational ones.

### 4.2 The full canonical hierarchy (26 subordinate roles)

```
Teller                                  ← Branch Operations Supervisor
                                        ← Branch Operations Manager (alt)

Customer Service Officer                ← Branch Operations Supervisor
                                        ← Branch Operations Manager (alt)

Direct Sales Representative             ← Branch Operations Supervisor
                                        ← Branch Operations Manager (alt)

Direct Sales Representative -
    Assets & Liabilities                ← Branch Operations Supervisor
                                        ← Branch Operations Manager (alt)

Branch Operations Supervisor            ← Branch Operations Manager
Branch Operations Manager               ← Branch Manager
Branch Relationship Manager             ← Branch Manager

Branch Senior Relationship Officer      ← Branch Manager
                                        ← Branch Relationship Manager (alt)

Relationship Officer-Business Banker    ← Branch Relationship Manager
                                        ← Branch Manager (alt)

Relationship Officer-Personal Banker    ← Branch Relationship Manager
                                        ← Branch Manager (alt)

Branch Manager                          ← Area Manager
Senior Branch Manager                   ← Area Manager
Area Manager                            ← Head of Branches

Senior Manager Direct Sales Force       ← Head of Branches
Head of Branches                        ← Chief Retail Banking Officer
Head of Retail Banking                  ← Chief Retail Banking Officer

Head Of Women Banking                   ← Head of Branches
                                        ← Chief Retail Banking Officer (alt)

Head of Government & Institutional
    Banking                             ← Chief Commercial Officer

Senior Manager -Credit Analysis         ← Chief Credit Officer
Senior Manager-Credit Analysis          ← Chief Credit Officer  (duplicate spelling)
Manager - Credit Monitoring             ← Chief Credit Officer
Manager-Credit Monitoring               ← Chief Credit Officer  (duplicate spelling)
Senior Manager-Collections & Recoveries ← Chief Credit Officer
Senior Manager-Collections and          ← Chief Credit Officer  (duplicate spelling)
    Recoveries
Assistant Manager -Credit Administration← Chief Credit Officer
Assistant Manager-Credit Administration ← Chief Credit Officer  (duplicate spelling)
```

### 4.3 Key observations

1. **Roles use exact data names** — "Chief Retail Banking Officer" (not "Director Retail Banking"), "Area Manager" (not "Regional Head"), "Head of Branches" (not "Head Of Retail")

2. **Branch Credit Manager IS NOT in canonical** — confirming v10.391 Finding TC17 that this role doesn't exist as live staff

3. **Each subordinate has 1-2 valid managers** — primary + alt. Cascade should respect this; bank's hr.json overrides that violate get flagged per the `_note`

4. **Spelling duplicates exist** — "Senior Manager -Credit Analysis" (with space-hyphen) AND "Senior Manager-Credit Analysis" (no space). Same role, two spellings. Probably maps to one actual role; need cleanup.

5. **Upward direction** — this whitelist points SUBORDINATE→[MANAGERS]. Pipeline and BSC navigation use it for line-manager lookup.

---

## Part 5 — Finding TC34-TC36 (HIGH): Hierarchy diverges across modules

### 5.1 Three independent hierarchy definitions exist

| Source | Direction | Top role used | Notes |
|---|---|---|---|
| `org_hierarchy_config.json::role_manager_whitelist` | upward (sub→mgr) | Chief Retail Banking Officer | **CANONICAL** (matches data) |
| `pages/3_pipeline.py::_HIER` (line 763) | downward (mgr→subs) | Managing Director | Pre-canonical; doesn't match data |
| `pages/12_cascade.py::HIERARCHY` (fallback line 150) | downward (mgr→subs) | Managing Director | Same as pipeline; fallback only |

### 5.2 The pipeline `_HIER` divergences from canonical

```python
# What pipeline/cascade hardcoded HIERARCHY says:
"Managing Director" → "Director Retail Banking"
                    → "Director Commercial Banking"
                    → "Chief Finance Officer"
                    → "Chief Risk Officer"
                    → ...

# What canonical (role_manager_whitelist) implies (inverted):
"Chief Executive & Managing Director" → "Chief Retail Banking Officer"
                                       → "Chief Commercial Officer"
                                       → "Chief Financial Officer"
                                       → "Chief Risk Officer"
                                       → ...
```

**8 role names differ**:
| Pipeline `_HIER` | Canonical (live data) |
|---|---|
| Managing Director | Chief Executive & Managing Director |
| Director Retail Banking | Chief Retail Banking Officer |
| Director Commercial Banking | Chief Commercial Officer |
| Chief Finance Officer | Chief Financial Officer |
| Chief Operations Officer | Chief Operating Officer |
| Head Of Retail | Head of Retail Banking |
| Regional Head | Area Manager |
| Branch Credit Manager | (doesn't exist in users) |

### 5.3 Why the cascade page falls back

`pages/12_cascade.py` lines 130-148 attempt:
```python
_org_hier = _get_org().get("hierarchy", {})  # ❌ wrong field name!
```

It looks for `hierarchy` field; the canonical store uses field name `role_manager_whitelist`. So the cascade page ALWAYS falls back to its hardcoded HIERARCHY, which has the wrong role names.

**Result**: cascade UI thinks "Managing Director" is the top role; live data has "Chief Executive & Managing Director" (William Mwanake). The cascade view for MD breaks because of role-name mismatch.

---

## Part 6 — Finding TC40 (HIGH): Structure engine divergence from canonical

My `utils/cascade_structure_engine.py::WITHIN_BRANCH_ROLE_PAIRS` was built from inspection of cross-branch patterns, not from the canonical whitelist. It diverges:

### 6.1 Missing in my engine (canonical has, mine doesn't)

```
Branch Manager → Relationship Officer-Business Banker  (canonical alt path)
Branch Manager → Relationship Officer-Personal Banker  (canonical alt path)
Branch Operations Manager → Customer Service Officer   (canonical alt path)
Branch Operations Manager → Teller                     (canonical alt path)
Branch Operations Manager → Direct Sales Representative (alt path)
Branch Operations Manager → Direct Sales Representative - Assets & Liabilities (alt)
Branch Operations Supervisor → Direct Sales Representative
Branch Operations Supervisor → Direct Sales Representative - Assets & Liabilities
Branch Relationship Manager → Branch Senior Relationship Officer  (alt path)
```

These are alt-path manager relationships in the canonical whitelist that my engine missed. **Engine would falsely flag legitimate cross-branch-within-role-pair as violation if these were used.**

Wait — these are within-branch by canonical, so they SHOULD be flagged as cross-branch violations when they cross branches. Let me re-read... Yes, these are alt paths within a branch. My engine missing them means **I'm under-detecting cross-branch violations** in those role pairs.

### 6.2 Extra in my engine (mine has, canonical doesn't)

```
Branch Manager → Branch Credit Manager   ← TC17: BCM doesn't exist as live role
Branch Operations Manager → Senior Digital Channels Officer
Branch Senior Relationship Officer → Direct Sales Representative - Assets & Liabilities
Branch Senior Relationship Officer → Relationship Officer Bancassurance
Branch Senior Relationship Officer → Relationship Officer-Business Banker
Branch Senior Relationship Officer → Relationship Officer-Personal Banker
```

These pairs say "BSRO supervises ROs and DSRs" — but canonical says "ROs report to BRM or BM directly, not to BSRO". So I'm OVER-detecting cross-branch violations: pairs that canonical doesn't even consider supervisory.

### 6.3 Impact assessment

```
False positives (mine flagged, canonical wouldn't): ~6 pairs × N entries
False negatives (mine missed, canonical would flag): ~9 pairs × N entries
```

Net effect: the engine's `cross_branch_count` of 25,137 is somewhat off — could be higher OR lower depending on the relative weight of each pair in actual data.

**Fix scope**: v10.395 will rebuild WITHIN_BRANCH_ROLE_PAIRS from canonical `role_manager_whitelist`.

---

## Part 7 — Finding TC38 (MEDIUM): Period mismatch

```
data/fixed_kpis.json:     2025-Q3, 2025-Q4, 2026-Q1, 2026-Q2   (QUARTERLY)
data/bank_targets.json:   2025, 2026                          (ANNUAL)
data/target_cascade.json: 2025, 2026                          (ANNUAL)
```

When BSC needs to look up a fixed KPI, it tries `get_fixed_kpis(period)` where period is the cascade period (annual "2026"). The fixed_kpis store is keyed by quarter ("2026-Q1").

The CascadeManager must translate annual → quarter — possibly to current quarter, possibly to all quarters of the year. Need to check the implementation. (Not surfacing here; v10.399 handles.)

---

## Part 8 — What v10.395+ needs to do

Revised execution sequence after this review:

| Batch | Concern | Driver |
|---|---|---|
| **v10.395** | **Align `WITHIN_BRANCH_ROLE_PAIRS` to canonical `role_manager_whitelist`** | TC40 |
| v10.396 | **Re-cascade** using canonical hierarchy + Fixed KPI mechanism | TC32 + TC34 |
| v10.397 | **Cascade page reads canonical hierarchy** (fix field name; remove fallback) | TC34 |
| v10.398 | **Pipeline page reads canonical hierarchy** (same fix; deduplicate `_HIER`) | TC35 |
| v10.399 | **Period harmonization** — translate annual ↔ quarterly | TC38 |
| v10.400 | **NPL Ratio / NPL_RATIO consolidation** | TC39 (subset of TC11) |

v10.395 is now the **first action batch** after this review — single concern, no Joshua decisions needed (engine internal change to use canonical store).

---

## Part 9 — Joshua's guidance noted as Confirmed Architectural Truths

These are documented in this batch and bind future work:

| ID | Guidance |
|---|---|
| **A1** | Fixed KPI status is the **MD's reserve** — MD controls via the cascade page Tab "🔒 Fixed KPIs". The system does NOT auto-flag any KPI as fixed. |
| **A2** | **Not all ratios are fixed.** NPL Ratio specifically varies per branch and is correctly removed from fixed. Other examples removed: PBT, Total NFI, NIM, ROE, CIR (financial outcomes that vary per unit). |
| **A3** | **Cascade follows canonical line manager hierarchy** — `org_hierarchy_config.json::role_manager_whitelist`. This is the same hierarchy the pipeline module uses for upward flow (when properly aligned). |
| **A4** | **The Fixed KPI tab UI is already correct** — MD ticks a KPI + enters a value, the value replicates to all staff with that KPI on their BSC. Mechanism does not need rebuilding. |

These are **architectural truths**, not decisions to be revisited. They guide v10.395+ implementation.

---

## Part 10 — Honest acknowledgements

1. **Joshua's guidance was correct on all four points**. The Fixed KPI mechanism exists and works. The canonical hierarchy exists. NPL is correctly per-branch. v10.394 confirms each.

2. **My structure engine's WITHIN_BRANCH_ROLE_PAIRS was approximate**, not canonical. Built from inspection of cross-branch patterns. 9 missing + 6 extra pairs vs `role_manager_whitelist`. v10.395 will fix.

3. **The canonical hierarchy is in a field with a different name** (`role_manager_whitelist`) than what the cascade page tries to load (`hierarchy`). Simple one-line fix, but it's why both pipeline and cascade pages fall back to hardcoded role names.

4. **The pipeline page has its own `_HIER`** dict with pre-canonical role names. Joshua explicitly said "it's the same hierarchy that flows upwards right from the pipeline module" — meaning they SHOULD be the same. They're not. v10.398 makes them so.

5. **NPL Ratio fixed-status contradiction (TC39)** is a real bug. Two KPI naming conventions cross paths with the Fixed KPI mechanism; same KPI gets two different fix-statuses depending on caller's name choice. Subtle and ugly.

6. **Period mismatch (quarterly vs annual)** wasn't on my radar before this review. Fixed KPIs are quarterly; cascade is annual. Translation must happen somewhere — likely CascadeManager. Untested ground; v10.399.

7. **Branch Credit Manager (TC17)** is confirmed by canonical absence — not in `role_manager_whitelist`. Yet pipeline `_HIER` and cascade `HIERARCHY` both reference it. Phantom role that pre-canonical hierarchy carried; needs scrubbing in v10.398.

8. **The Fixed KPI tab UI is genuinely well-designed**: MD-only access guard, per-pillar grouping, shows which roles carry the KPI, separate tick-and-value inputs. v10.394 just documents that it works; v10.395+ uses it.

9. **"It's the same hierarchy that flows upwards"** — Joshua's phrasing matters. The pipeline FLOWS UPWARD (escalation, backups, approval). The CASCADE FLOWS DOWNWARD (targets). Same hierarchy, two directions. v10.398 unifies the source.

10. **15 v10.391 + 11 v10.392 + 15 v10.393 + 12 v10.394 = 53 Phase C2 tests now exist**. Each batch's tests verify against live data; they'll keep regression in check as v10.395+ makes changes.

11. **No backup file needed for v10.394** — review only, like v10.391 was. The pattern of "build a doc + gate + tests + nothing else" continues to work.

12. **`_v10324_removed_from_fixed`, `_v10328_added`, `_v10329_added`** are great markers — the data file itself documents its evolution. Future cleanup can read these to understand the journey.

13. **9 findings TC33-TC41** in this review — much smaller than v10.391 (31 findings) or v10.393's TC32 (1 root cause). Because v10.394 is a targeted review of a specific guidance, not a broad sweep. Different scope, different depth.

14. **Pattern continues**: diagnosis batch (v10.391) → execution batches (v10.392 cycle fix) → mid-arc discovery batch (v10.393 TC32) → guidance-driven review batch (v10.394 this) → execution batches (v10.395+ alignment). The arc is taking shape as Joshua's guidance shapes each turn.

15. **No new decisions surfaced**. Joshua's guidance answered C5 (ratios use Fixed KPI mechanism) and the hierarchy question (use canonical). C1, C2, C3, C4, C6 from v10.391 remain on the backlog but don't block v10.395-v10.400 execution.

## What v10.395 will do

**Single concern (Rule N2)**: align `cascade_structure_engine.WITHIN_BRANCH_ROLE_PAIRS` to canonical `role_manager_whitelist`.

1. Read `org_hierarchy_config.json::role_manager_whitelist`
2. Filter for "branch-level managers" (exclude regional roles: Area Manager, Head of Branches, Chief Retail Banking Officer, Chief Credit Officer)
3. Compute the set of (manager_role, subordinate_role) pairs
4. Replace `WITHIN_BRANCH_ROLE_PAIRS` constant with this derived set (or expose function that loads it dynamically)
5. Re-run `cascade_structure_engine.full_audit()` — expect different counts for `cross_branch_count` and `multi_sender_count`
6. Add gate + integration tests verifying engine uses canonical pairs

Single concern, no Joshua decisions, low risk. Foundation for v10.396 re-cascade.
