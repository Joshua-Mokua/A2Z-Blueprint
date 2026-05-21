# Changelog — v10.357 Virtual Bank Readiness Audit

**Date:** 2026-05-13
**Phase:** 4 (forty-second arc — reconnaissance before live bring-up)
**Audit:** G243 added (passes in ~5.6s isolated)
**Tests:** 14/14 PASSED in `test_v10357_virtual_bank_readiness.py`
**Page smoke:** 123/123 PASS + 0 static findings + 14/14 dynamic renders pass
**Verifier:** 145/145 checks pass on a clean extract
**G162 Baseline:** 4022 (51 consecutive zero-drift batches)
**Master prompt:** v4.0 → v4.1 (lockstep maintained — first batch under recovered discipline)

---

## Your ask

> "continue" (after v10.356 master prompt sync) — and the prior commitment to "bring this system as is required" with the explicit objective: virtual bank live bring-up, all 487 staff working with BSCs updating, EDMS capturing, CIM running, SLAs ticking, stress testing, everything interconnected, production-grade.

My honest position at the start of this batch: **going straight to a Football Team Test harness without first surveying the existing virtual-bank infrastructure risks chasing a moving target.** Reconnaissance is cheap; action without reconnaissance is expensive. v10.357 is the reconnaissance batch.

## What v10.357 delivered

### `utils/virtual_bank_readiness.py` (425 lines)

A probe-only module — does not change platform state, does not generate data, does not seed any bank. Produces a JSON-serializable readiness report consumed by v10.358+ batches.

Five distinct probes:

| Probe | What it measures |
|---|---|
| `_probe_module` (×8) | Each simulator module loads + self_test passes |
| `_probe_boot` | VirtualBankCore + Simulator instantiate + 5-day run executes end-to-end |
| `_probe_coverage` | virtual_bank.coverage_report — active staff, KPI mapping, BSC coverage % |
| `_probe_scenarios` | 4 sample scenarios via ScenarioRunner with test engine bundle |
| `_probe_chain` | Football Team Test 7-link chain status (WIRED / PARTIAL / MISSING) |

The synthesis function `capture_readiness_report()` runs all five and produces a `ReadinessReport` dataclass. Overall status is one of: `READY`, `READY_BUT_NOT_VERIFIED`, `BLOCKERS`, `UNKNOWN`. Each gap surfaces as either a blocker (must be fixed before proceeding) or a note (information, not blocking).

### Headline findings at v10.357 capture

**Modules (8/8 load + self-test green):**

| Module | LOC | Self-test |
|---|---|---|
| `utils.virtual_bank` (foundation) | 717 | n/a |
| `utils.virtual_bank_core` (mock FLEXCUBE) | 1,167 | ✓ 27 tests, 0.00s |
| `utils.virtual_bank_simulator` (daily ops) | 1,323 | ✓ 23 tests, 0.00s |
| `utils.scenario_simulator` (186 scenarios) | 18,026 | ✓ 18 tests, 0.17s |
| `utils.stress_testing` (CBK supervisory) | 591 | ✓ 15 tests, 0.00s |
| `utils.strategy_simulator` | 628 | n/a |
| `utils.hybrid_scheduling_simulator` | 491 | n/a |
| `utils.liquidity_stress` | 744 | ✓ 18 tests, 0.00s |
| **Total** | **23,687** | **101 internal tests pass** |

**Boot probe:** VirtualBankCore + Simulator instantiate cleanly. 5-day simulation runs end-to-end in 0.00s. Generates **0 customers, 0 accounts, 0 transactions** because the bank starts empty. **The seed-the-bank step is the missing prerequisite.** The pipeline is sound; the data isn't there to flow through it.

**Coverage gap (the live bring-up's primary KPI):**
- 1,439 active staff (vs the canonical 487 mentioned in the brief — the larger number includes synthesized hierarchy)
- **100% have KPI mappings** (every staff knows what they should be measured on)
- **2.78% have BSC actuals** (only 40 staff have current-period numbers landed)
- 22/22 departments have a clean BSC submission path (the plumbing works)
- 34 dangling refs + 26 unused KPIs in the library (housekeeping deferred)

**Scenario harness:** Sample of 4 scenarios via `ScenarioRunner` with `_build_test_engine_bundle`:
- LI-01 LCR_COMPLIANT — PASS (2 assertions)
- LI-02 LCR_BREACH — PASS (1 assertion)
- IRRBB-01 — PASS (1 assertion)
- CAP-01 CBK_DUAL_THRESHOLD — PASS (3 assertions)

**4/4 pass in 0.00s.** The 186-scenario harness is real and executable. v10.358+ work can confidently lean on it.

### Football Team Test chain — explicit classification

| # | Link | Status | Notes |
|---|---|---|---|
| 1 | Teller action → CBS | **PARTIAL** | Simulator generates txns in VirtualBankCore memory but does not persist to `cbs_data/*.json`. Bridge module is the v10.358 priority. |
| 2 | CBS → actuals_engine | ✅ WIRED | `compute_actuals_from_cbs` reads cbs_data/, writes actuals_*.xlsx |
| 3 | actuals_engine → YoY sidecar | ✅ WIRED | v10.355's `refresh_yoy` (caller-orchestrated since v10.356) |
| 4 | YoY → BSC display | ✅ WIRED | v10.355's expander in `pages/1_perform.py` |
| 5 | BSC → branch score | ✅ WIRED | `pages/1_perform.py` rollups |
| 6 | Branch → regional | ✅ WIRED | branch_ranking page + regional aggregation |
| 7 | Regional → MD tile | **PARTIAL** | Bank-targets binding incomplete per roadmap item 2. The mechanical rollup exists; the MD-level "on track?" tile that Charter §2 requires is not yet end-to-end. |

**5/7 WIRED. 2/7 PARTIAL. End-to-end verification status: NOT YET PASSING.**

This is the clearest picture of where Charter §2 stands. The blockers are concrete — two specific links — not "everything needs work." That's the value of reconnaissance.

### Audit gate G243

Locks the readiness baseline. Validates:
1. All 8 simulator modules load
2. All self-tests that exist pass
3. Boot probe completes end-to-end (5-day run executes)
4. ≥1000 active staff resolved by virtual_bank.coverage_report (Ecobank-scale guard)
5. Scenario sample passes 4/4

**The chain link breakdown (5 WIRED + 2 PARTIAL) is recorded but NOT enforced** at v10.357 — it is informational reconnaissance. Future batches close PARTIAL → WIRED and the gate can ratchet to require WIRED. Pattern R5 — Ratchets, not heroics applied incrementally.

G243 isolated runs in ~5.6s. Adds reasonable cost given how much it surveys.

### Schema lock `data/_schemas/virtual_bank_readiness.schema.json`

Pattern Q — `validate_before_save` on every save. Schema covers all 5 probes + their nested fields. Auto-registers `virtual_bank_readiness.json` as G230-protected.

### Master prompt v4.1 — lockstep maintained

This is the **first batch under the recovered v4.0 lockstep discipline.** Master prompt bumped to v4.1, State-of-Play updated to v10.357, version history shows the clean v4.0 → v4.1 transition. G242 verifies the lockstep — newest prompt now `Master_Prompt_v4.1.md`, references v10.357, all 11 mandatory standards still present.

The discipline that eroded for 240 versions held for the second consecutive batch.

## Files changed

| File | Change |
|---|---|
| `utils/virtual_bank_readiness.py` | NEW — 425 lines, 5 probes + synthesis |
| `data/_schemas/virtual_bank_readiness.schema.json` | NEW — schema lock |
| `data/virtual_bank_readiness.json` | NEW — captured report (READY_BUT_NOT_VERIFIED, 0 blockers, 2 notes) |
| `scripts/audit.py` | NEW gate G243 `gate_virtual_bank_readiness` |
| `scripts/verify_local_state.py` | Extended to 145 checks |
| `tests/integration/test_v10357_virtual_bank_readiness.py` | NEW — 14 tests |
| `docs/Master_Prompt_v4.1.md` | NEW — lockstep bump from v4.0 |

## Verified outcome

| Metric | Before → After v10.357 |
|---|---|
| Audit gates | 242 → **243** (G243 added) |
| Protected data files | 11 → **12** (virtual_bank_readiness.json added) |
| Page smoke | 123/123 PASS (preserved) |
| Static AST | 0 findings (preserved) |
| Dynamic render | 14/14 effective PASS (preserved) |
| Tests | +14 in v10.357 file, all passing |
| Verifier | 137 → **145 checks** |
| Master prompt | v4.0 (v10.355) → **v4.1 (v10.357)** — lockstep |
| G162 baseline | 4022 (**51 consecutive zero-drift batches**) |

## Honest acknowledgements

1. **Reconnaissance only, no platform change.** v10.357 deliberately produces no new user-facing behavior. The platform behaves identically before and after this batch. The value is informational: a structured readiness report with chain-status classification that v10.358+ can act on with confidence.

2. **Boot probe ran against an empty bank.** The 5-day simulation executed end-to-end but generated 0 transactions because VirtualBankCore starts with 0 customers, 0 accounts, 0 branches. This confirms the simulator pipeline works mechanically; it does not test the data-generation pathway. **A seed-the-bank step is the prerequisite for meaningful simulation runs.** Flagged as a note (not a blocker) because the empty-run completing successfully is itself a useful signal.

3. **Sample of 4 scenarios, not the full 186.** Running all 186 would take time (the engine bundle has nontrivial setup cost) and would dwarf the readiness report with scenario-specific details. The sample (LI-01, LI-02, IRRBB-01, CAP-01) covers DEPOSIT_LIQUIDITY, OPERATIONS_TREASURY, and RISK_COMPLIANCE categories — enough to verify the harness is alive. A future batch can run the full set if desired.

4. **Chain classification is conservative.** WIRED requires the mechanism to be both PRESENT and END-TO-END VERIFIED. PARTIAL means mechanism present but the full chain isn't yet exercised. By this standard, Link 1 (teller→CBS) is PARTIAL even though the simulator generates real transactions — they don't yet land in cbs_data/*.json. Some readers might disagree with the conservative call; the audit notes section makes the reasoning explicit so others can challenge it.

5. **40 active staff with BSC actuals does not mean "the platform serves 40 staff."** The 40 are those whose actuals have been computed and persisted into `data/bsc_actuals_*.json`. The other 1,399 have KPI mappings + functional submission paths — the actuals just haven't been driven through yet. The path to 100% is exercising the live actuals engine end-to-end across all departments.

6. **The 1,439 active staff number is larger than the brief's "487 staff" figure.** The 487 likely refers to a specific role/category cut. The 1,439 includes synthesized manager hierarchy + role variants from users.json. Reconciling the two is housekeeping; both numbers are honest, they measure different cuts.

7. **strategy_simulator and hybrid_scheduling_simulator lack self_test functions** but load cleanly. The probe records this as "n/a" rather than failure. If these modules are intended to be production-grade, they should grow self_tests; if they're scaffolding, that should be documented. Out of scope for this batch.

## On your end

1. Close Streamlit
2. Delete leftover subfolder extracts
3. Extract `a2z_v10357_session_cumulative.zip` flat into the A2Z workspace, overwriting everything
4. Run `python scripts\verify_local_state.py` → expect **ALL 145 CHECKS PASSED**
5. **Read `data\virtual_bank_readiness.json`** — this is the survey output. The numbers will differ from sandbox in some places (your localhost has more CBS data) but the chain status should match.
6. Read `docs\Master_Prompt_v4.1.md` — the lockstep-maintained constitution.
7. (Optional, takes >5min) Run audit → expect **243/243 PASS**
8. Run the readiness audit yourself any time:
   ```python
   python -c "from utils.virtual_bank_readiness import capture_readiness_report, format_readiness_summary; print(format_readiness_summary(capture_readiness_report()))"
   ```

## v10.358 — concrete roadmap from the audit

The reconnaissance produces a sequenced plan:

| Batch | Concern | Why this order |
|---|---|---|
| **v10.358** | Seed-the-bank helper | The Football Team Test cannot run against an empty bank. Single helper that populates VirtualBankCore from existing data sources (users.json staff, hr.json branches, kpi_library) into the structures expected by `add_customer` / `add_account` / `add_branch`. |
| **v10.359** | Link 1 bridge: teller→CBS | Persist simulator transactions to `cbs_data/*.json` so the downstream actuals_engine sees them. Closes Link 1 from PARTIAL → WIRED. |
| **v10.360** | Link 7: MD tile bank-targets binding | Roadmap item 2. Bank-targets in Target Cascade → MD BSC tile. Closes Link 7 from PARTIAL → WIRED. |
| **v10.361** | End-to-end Football Team Test | Integration test that fires a synthetic teller transaction, waits for the chain to propagate, asserts the MD tile changes. The actual Charter §2 acceptance criterion finally verifiable. |

After v10.361, Charter §2 passes. Then the live bring-up has a verified backbone to scale against.

Alternative orderings — open for discussion:
- v10.358 = seeding first vs Link 1 first (seeding is the harder constraint; Link 1 is the conceptual bridge)
- Defer Link 7 to a later batch and prioritize the seeding + Link 1 pair
- Insert a Link 1.5 batch that wires the EDMS / CIM / SLA capture modules into the chain before testing end-to-end

My recommendation: **v10.358 = seed-the-bank helper**, followed by Link 1, then Link 7, then the integration test. Each batch is independently shippable and each closes one specific gap surfaced by the audit.

Which way?
