# Changelog — v10.358 Seed-the-Bank Helper

**Date:** 2026-05-13
**Phase:** 4 (forty-third arc — Football Team Test backbone)
**Audit:** G244 added (passes in ~0.1s isolated)
**Tests:** 14/14 PASSED in `test_v10358_seed_the_bank.py`
**Page smoke:** 123/123 PASS + 0 static findings + 14/14 dynamic renders pass
**Verifier:** 153/153 checks pass on a clean extract
**G162 baseline:** 4022 (52 consecutive zero-drift batches)
**Master prompt:** v4.1 → v4.2 (lockstep maintained — third consecutive batch)

---

## Your ask

> "proceed" (with v10.358 — seed-the-bank helper, per the v10.357 readiness audit's concrete v10.358+ roadmap)

The v10.357 audit identified: "Boot probe ran the simulator against an empty VirtualBankCore — 0 customers/accounts/transactions generated. A seed-the-bank step is the prerequisite for meaningful end-to-end runs." This batch closes that prerequisite.

## What v10.358 delivered

### `utils/virtual_bank_seed.py` (~500 lines)

A deterministic seeder. Five major pieces:

**1. ECOBANK_BRANCHES dict (21 branches).** Sourced from `utils.core.BRANCH_REGION` — the real Ecobank Kenya branch list (Mombasa, Nyali, Malindi, Nairobi CBD, Thika, Eldoret, Kisumu, etc.) with South/Central/North regions. Duplicated in the seed module (rather than imported) because `utils.core` depends on streamlit, and the seeder runs in non-Streamlit contexts (audit gates, CLI tests). G244 locks the sync — if utils.core changes, the seed module must follow.

**2. SeedConfig dataclass** with three scale presets:
- `SeedConfig.small()` — 100 customers / 200 accounts / 30 loans / 21 branches / 30 RMs. Default for unit tests + Football Team Test harness. Runs in ~10ms.
- `SeedConfig.medium()` — 1,000 customers
- `SeedConfig.large()` — 10,000 customers (for stress testing)

Each config carries segment mix (RETAIL 70% / SME 20% / CORPORATE 6% / HNW 3% / PRIVATE_BANKING 1%), account-type mix (SAVINGS 55% / CURRENT 30% / FIXED_DEPOSIT 10% / OVERDRAFT 5%), balance ranges per segment, loan principal ranges per segment, and a `base_seed` string for determinism.

**3. RM sourcing from `data/users.json`.** `_select_rms_from_users()` filters active users with roles matching "Relationship" or "RM" patterns and returns their staff_codes. 419 active RMs available in users.json; the small config pulls 30 of them. Falls back to synthetic `RM_001` codes if users.json is unavailable.

**4. Deterministic generation via Park-Miller LCG.** `_deterministic_index()` is a 5-line linear-congruential generator. Same seed → same sequence on every Python version. No `random` module dependence. Branch assignment, RM assignment, balance values, account types, loan principals — all derived from seeded indices.

**5. `seed_virtual_bank(bank, config)` public API.** Returns `(bank, SeedResult)` where `SeedResult` is a structured summary (n_branches, n_customers, n_accounts, n_loans, total_deposits_kes, total_loans_kes, duration_s, notes).

### Wiring into readiness audit

`utils/virtual_bank_readiness.py::_probe_boot` updated to seed the bank before running the 5-day simulation. The bank now has 100 customers, 200 accounts, 30 loans across 21 branches at simulation start — and the simulator generates ~2,645 transactions over 5 days. **The v10.357 "empty bank" note is gone.**

If the seed step fails for any reason, the probe falls back to running against an empty bank (preserves the v10.357 pipeline-integrity check). Surfaced via `probe.error` field so regression is visible.

### G244 audit gate

Locks three invariants:

1. **Branch sync.** `ECOBANK_BRANCHES` count matches `utils.core.BRANCH_REGION` count. Parses utils/core.py source to count BRANCH_REGION entries; flags if the two drift.
2. **Determinism.** Two consecutive `seed_virtual_bank(config=SeedConfig.small())` runs produce identical `total_deposits_kes`, `total_loans_kes`, and `n_accounts`. Non-determinism breaks the v10.361 Football Team Test integration test's assertion model.
3. **Minimum viable scale.** Small config produces ≥50 customers and nonzero deposits. Catches regressions where the seeder silently produces empty banks.

Runs in 0.06s isolated. Adds zero meaningful cost to the full audit.

### Self-test (10 tests)

`virtual_bank_seed.self_test()` validates:
- ECOBANK_BRANCHES has 21 entries
- Small config defaults are sensible
- Seeder runs end-to-end
- Result counts match config
- Determinism (two runs produce same totals)
- Totals are nonzero
- Referential integrity (no orphan accounts/loans, branch codes resolve)
- Format summary works

All 10 pass in ~50ms. Mirrors the pattern used by virtual_bank_core / virtual_bank_simulator / scenario_simulator etc.

## Files changed

| File | Change |
|---|---|
| `utils/virtual_bank_seed.py` | NEW — seeder module (~500 lines) |
| `utils/virtual_bank_readiness.py` | `_probe_boot` now seeds the bank before simulation |
| `scripts/audit.py` | NEW gate G244 `gate_seed_determinism` |
| `scripts/verify_local_state.py` | Extended to 153 checks |
| `tests/integration/test_v10358_seed_the_bank.py` | NEW — 14 tests |
| `docs/Master_Prompt_v4.2.md` | NEW — lockstep bump from v4.1 |

## Verified outcome

| Metric | Before v10.358 → After v10.358 |
|---|---|
| Audit gates | 243 → **244** (G244 added) |
| Boot probe transactions | 0 → **~2,645** over 5 days |
| Boot probe customers | 0 → **100** (configurable up to 10,000) |
| Boot probe accounts | 0 → **200** |
| Boot probe loans | 0 → **30** |
| Football Team Test chain | 5/7 WIRED, 2/7 PARTIAL (preserved — v10.358 is infrastructure) |
| Page smoke | 123/123 PASS (preserved) |
| Static AST | 0 findings (preserved) |
| Dynamic render | 14/14 effective PASS (preserved) |
| Tests | +14 in v10.358 file, all passing |
| Verifier | 145 → **153 checks** |
| Master prompt | v4.1 → **v4.2** — lockstep |
| G162 baseline | 4022 (**52 consecutive zero-drift batches**) |

## Honest acknowledgements

1. **Synthetic customer names from a fixed pool.** The pool is small (20 first names + 20 last names + 10 company prefixes / 5 suffixes + 7 corporate prefixes / 7 sectors). At small scale (100 customers) this means some collisions — Wanjiru Mwangi might appear twice. At scale, more collisions. This is acceptable for the test harness; real production would want a larger pool or external name source. Flagged for future improvement, not blocking.

2. **All customers onboard on day 0.** The seeder sets every customer's `onboarding_date` to the config's `base_date` (default 2026-01-01). The simulator advances them through transactions but the onboarding histogram is flat. Real banks have a multi-year customer-acquisition curve. Out of scope for v10.358; the simulator can be enhanced to age customers over time.

3. **No KYC document attachment.** Customers are created with `is_pep=False`, `sanctions_status="CLEAR"`. EDMS (customer documentation capture) is a separate concern — its integration with the seeded bank is a future batch.

4. **Loan portfolio bias.** First 30% of customers (by deterministic index) get loans. The v10.358 default doesn't randomize which customers have loans within the population. A real bank's loan portfolio is segment-correlated (more SMEs / CORPORATEs have loans than RETAILs). The seeder produces a representative-enough portfolio for the Football Team Test but not a CBK-publishable distribution.

5. **All loans are PERFORMING at seed time.** No NPLs, no delinquency. The simulator's `apply_credit_deterioration` scenario can introduce NPLs; the seeder doesn't pre-populate them. This is honest: a fresh seeded bank starts clean, and stress is added through scenarios.

6. **The seeder doesn't write to cbs_data/*.json.** v10.358 produces an in-memory populated bank. Persistence to CBS aggregates is v10.359's job (Link 1 bridge). Without persistence, the actuals_engine still won't see the seeded bank — but that's by design; v10.358 is the population step, v10.359 is the persistence step.

7. **Park-Miller LCG instead of `secrets`/`random`.** Park-Miller is the right tool for the job: deterministic, no Python-version drift, well-understood. It's not cryptographically secure — we don't need it to be. The seeder is producing test data, not cryptographic material.

8. **G244 sync check is best-effort.** Parses `utils/core.py` source with a regex to count BRANCH_REGION entries. If the source format changes (e.g. the dict is rewritten as a constructor call), the regex misses and the check silently passes. The determinism + scale checks remain hard.

## On your end

1. Close Streamlit
2. Delete leftover subfolder extracts
3. Extract `a2z_v10358_session_cumulative.zip` flat into the A2Z workspace, overwriting everything
4. Run `python scripts\verify_local_state.py` → expect **ALL 153 CHECKS PASSED**
5. **Run the seeder directly:**
   ```
   python -c "from utils.virtual_bank_seed import seed_virtual_bank, format_seed_summary; bank, r = seed_virtual_bank(); print(format_seed_summary(r))"
   ```
   Expect: 21 branches, 100 customers, 200 accounts, 30 loans, KES 71.7M deposits, KES 5.1M loans.
6. **Run the readiness audit to see the seeded boot probe:**
   ```
   python -c "from utils.virtual_bank_readiness import capture_readiness_report, format_readiness_summary; print(format_readiness_summary(capture_readiness_report()))"
   ```
   Expect: "Generated: 100 customers, 200 accounts, 2645 transactions" (up from 0/0/0 in v10.357).
7. Read `docs\Master_Prompt_v4.2.md` — third consecutive lockstep batch.
8. (Optional, takes >5min) Run audit → expect **244/244 PASS**

## v10.359 candidate — Link 1 teller→CBS persistence bridge

The seeder populates VirtualBankCore in memory. The simulator generates VirtualTransaction records. **Nothing currently writes them to `cbs_data/*.json`**, which means `actuals_engine.compute_actuals_from_cbs` never sees the simulated activity.

**v10.359 closes Link 1** by adding a bridge module — call it `utils/virtual_bank_cbs_writer.py` or similar — that takes a VirtualBankCore (or just the transaction list) and writes the aggregates the actuals_engine expects. Key files to produce:
- `cbs_data/deposits_aggregate.json` — sum of deposit-account balances
- `cbs_data/loans_aggregate.json` — sum of outstanding loan principals
- `cbs_data/npl_aggregate.json` — NPL stage 3 amounts (zero on a fresh seed; non-zero after scenarios apply credit deterioration)
- `cbs_data/customer_aggregate.json` — total customer count
- `cbs_data/dormant_aggregate.json` — dormant account count

These are exactly the files v10.354's baseline snapshot mechanism already knows how to read. The bridge writes them; the actuals_engine reads them; the YoY sidecar updates; the BSC display shows the change.

After v10.359, simulating activity in the virtual bank → moves the BSC numbers. That's the start of the Football Team Test chain working end-to-end.

Then v10.360 = MD tile bank-targets binding (Link 7). v10.361 = the full integration test that fires a synthetic teller transaction and asserts the MD tile changes.

Want me to proceed with v10.359?
