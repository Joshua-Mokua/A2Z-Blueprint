# CHANGELOG v10.40 — RISK ARC CONTINUES · MARKET RISK LIMITS & BREACH MANAGEMENT

**Audit:** 128/128 PASS — **122nd consecutive clean.**
**Tests:** 897 integration (+26 from v10.39's 871) + 19 self-tests on `market_risk_limits`.
**Status:** Risk arc continues. Market Risk now has operational teeth — limits to enforce + breach detection + escalation. **2 ENH-MR-* standards activated. 111/254 active.**

---

## Why limits before more measurement

The v10.39 foundation can compute VaR, ES, and sensitivities. But measurements without limits are academic — they tell you what the risk *is*, not whether it's *acceptable*. The natural next batch is the operational layer that turns measurements into actionable signals.

Building Market Risk Limits before expanding into trading book boundary, credit risk, or operational risk gives every subsequent risk module the same pattern: build the measurement engine, register the limits, route the breaches.

## What v10.40 ships

### `utils/market_risk_limits.py` (855 lines, 19 self-tests) — ENH-MR-006 + ENH-MR-007

Three limit types covering the operational decisions for market risk:

| LimitType | Scope choices | What it constrains |
|---|---|---|
| `CONCENTRATION` | SINGLE_FACTOR or FACTOR_CLASS | Per-factor or per-class exposure ceiling (e.g., USD/KES ≤ 2bn, total FX ≤ 5bn) |
| `VAR_LIMIT` | PORTFOLIO only | Daily VaR ceiling at specified (confidence, horizon) |
| `ES_LIMIT` | PORTFOLIO only | Expected Shortfall ceiling at FRTB-IMA 97.5% / 10-day |

Three `LimitScope` enums (SINGLE_FACTOR / FACTOR_CLASS / PORTFOLIO). Validation in `RiskLimit.__post_init__` enforces consistency:

- CONCENTRATION cannot be PORTFOLIO scope
- VAR_LIMIT and ES_LIMIT only allow PORTFOLIO
- VAR_LIMIT and ES_LIMIT require both `confidence` and `horizon_days`
- SINGLE_FACTOR requires `factor`; FACTOR_CLASS requires `factor_class`; PORTFOLIO sets neither

### Severity bands

Four `BreachSeverity` levels mapped from utilization percentage:

| Severity | Utilization | Action level |
|---|---|---|
| `WITHIN_LIMIT` | < 80% | Informational — no action |
| `WARN` | 80% – 99.99% | Treasury + Risk Operations |
| `BREACH` | 100% – 119.99% | ALCO + CRO (or Board if BOARD-approved limit) |
| `SEVERE_BREACH` | ≥ 120% | Board Risk Committee + CRO + Treasurer |

Escalation scaling is **mechanical** — utilization determines target. Per Rule 7, the monitor never auto-executes remediation; alerts flow into existing approval workflows (`treasury_agents.PaymentReviewAgent` or human approval). EU AI Act Art 14 human oversight preserved at every severity.

### `LimitRegistry` — immutable history

Limits are **frozen** dataclasses. To "change" a limit, deactivate the old one and register a new one with a new `effective_date`. This pattern preserves full audit history — at any point in time you can answer "what was the active VaR limit on date X?".

```
register(limit)         # raises if limit_id already exists
deactivate(limit_id)    # keeps in storage, marks inactive
get(limit_id)           # always retrievable (active or not)
all_active()
by_type(LimitType.CONCENTRATION)
by_factor(RiskFactor.FX_USDKES)   # returns single-factor + class limits
```

`by_factor` is intentional: a query for "what limits apply to my USD/KES position" returns both the SINGLE_FACTOR limit on USD/KES *and* the FACTOR_CLASS limit on FOREIGN_EXCHANGE.

### `LimitMonitor` — diagnostic, not active

Three check methods + one orchestrator:

```
check_concentration(exposures_by_factor)
    → aggregates by class for FACTOR_CLASS limits
    → uses absolute value (net SHORT counts)

check_var(observed_var_kes, confidence, horizon_days)
    → matches ONLY exact (confidence, horizon) tuples
    → a 99%/1d limit doesn't trigger on 95%/1d obs

check_es(observed_es_kes, confidence, horizon_days)
    → same exact-match semantics

run_pass(...)
    → orchestrates all three; returns MonitorReport
```

A single `run_pass` call returns one `MonitorReport` with `n_within / n_warn / n_breach / n_severe` counts plus the full `alerts` tuple.

### Per Rule 1 — `BreachAlert` carries everything

```
alert_id              # deterministic = limit::date::obs::sev (dedup-safe)
severity              # BreachSeverity enum
limit_id              # which limit
limit_type            # CONCENTRATION / VAR_LIMIT / ES_LIMIT
scope                 # SINGLE_FACTOR / FACTOR_CLASS / PORTFOLIO
observed_kes          # what was observed (Decimal)
threshold_kes         # what was the limit (Decimal)
utilization_pct       # observed / threshold × 100 (Decimal, 2dp)
factor                # if applicable
factor_class          # if applicable
suggested_action      # human-readable recommendation per severity × type
escalation_target     # who gets notified
framework_refs        # regulatory provenance from the limit
notes
```

Alert ID determinism enables audit-trail dedup: replay a breach today and the same `alert_id` is produced. Different observation values produce different IDs even on the same limit.

### 5 default illustrative limits

Per CBK PG/04 §4 + BCBS d352 §A.4. These ship as constants and as a pre-populated registry via `build_default_registry()` for tests, demos, and as the wiring template for production:

| ID | Type | Scope | Threshold | Approval |
|---|---|---|---|---|
| `VAR_99_1D_TRADING_BOOK` | VAR_LIMIT | PORTFOLIO | KES 50m daily | BOARD |
| `ES_975_10D_TRADING_BOOK` | ES_LIMIT | PORTFOLIO | KES 150m | BOARD |
| `CONC_FX_USDKES_NET` | CONCENTRATION | SINGLE_FACTOR (FX_USDKES) | KES 2bn | ALCO |
| `CONC_FX_TOTAL` | CONCENTRATION | FACTOR_CLASS (FOREIGN_EXCHANGE) | KES 5bn | ALCO |
| `CONC_EQUITY_TOTAL` | CONCENTRATION | FACTOR_CLASS (EQUITY) | KES 1bn | ALCO |

These are illustrative — actual production limits would be board-approved per the bank's own risk appetite statement.

## 5 LIMITS-* scenarios extending the library 24 → 29

| ID | What it verifies |
|---|---|
| `LIMITS-01` | USD 1bn vs 2bn limit (50%) → WITHIN_LIMIT, no breaches |
| `LIMITS-02` | VaR 55m vs 50m limit (110%) → BREACH, ALCO+CRO escalation |
| `LIMITS-03` | ES 195m vs 150m limit (130%) → SEVERE_BREACH, Board escalation |
| `LIMITS-04` | USD 3bn + EUR 2bn + GBP 1bn = 6bn vs 5bn class limit (120%) → SEVERE_BREACH; AND USD 3bn vs 2bn single-factor limit (150%) → SEVERE_BREACH simultaneously |
| `LIMITS-05` | Per Rule 1 — BreachAlert carries observed + threshold + utilization + framework_refs + deterministic alert_id |

All 5 PASS when the 4 modules (factors / sensitivities / var / limits) are wired into `ScenarioRunner(engines=…)`. 15 assertions total all green.

## Standards registry — 2 new active

| ID | Title | Severity | Engines |
|---|---|---|---|
| ENH-MR-006 | Market Risk Limit Framework | HIGH | `market_risk_limits` |
| ENH-MR-007 | Limit Breach Detection & Escalation | HIGH | `market_risk_limits` |

`subcategory="market_risk"`, `priority_tier="A"`, `implementation_batch="v10.40"`.

**Active total: 111 / 254.**

## Engine Hub Tier 22 added

"Tier 22 — Market Risk Limits & Breach Management (v10.40+)" documents the single new module with full description of the three LimitType × three LimitScope matrix, the four severity bands with escalation targets, and the diagnostic-not-active design per Rule 7.

## G128 anti-entanglement check

```
Modules scanned:  305 → 306  (+1 module)
Internal imports: 759 → 761  (+2 imports — limits → factors)
HARD failures:      3 → 3    (unchanged)
Status: STABLE
```

**One new module + 2 new internal imports introduced zero new structural debt.** The G128 baseline mechanism continues to do its job — every batch goes through the audit gate, and new code is mechanically prevented from becoming entangled.

## Forward-compat fix in v10.39 test

The v10.39 test `TestV1039StandardsRegistry.test_5_enh_mr_standards_active` originally asserted *exactly* 5 ENH-MR standards. v10.40 added 2 more (ENH-MR-006, ENH-MR-007), bringing the total to 7. The test now filters by `implementation_batch == "v10.39"` to remain forward-compatible — it asserts the v10.39 batch produced exactly 5 standards, regardless of how many later batches add. This is the standard pattern for cross-batch assertions; future batches (v10.41+) won't break it.

## Honest scope notes

1. **No new audit gate.** v10.40 is mid-arc. The Risk arc closure gate (G129) will come at the eventual closure batch, mirroring the Treasury pattern (v10.33 opened, v10.37 closed with G127 — no per-batch gates in between).
2. **Limits not connected to a database.** The default registry is in-memory. Production wiring (loading limits from PostgreSQL, persisting alert audit trail to `core_audit`) is a separate workstream. The `LimitRegistry` API is designed to be straightforward to swap to a DB-backed implementation.
3. **No real-time breach feed.** `LimitMonitor.run_pass` is a pull-based check. A push-based stream that calls `run_pass` on every position update is downstream wiring (composes with `treasury_agents.AgentOrchestrator`).
4. **Alert action layer minimal.** `suggested_action` and `escalation_target` are text fields. They give a human the right framing — they don't auto-create tickets or send notifications. Action wiring (e.g., to ServiceNow, Slack, or `treasury_agents.PaymentReviewAgent`) is downstream.
5. **Per Rule 7 — diagnostic boundary held.** The monitor never closes positions, never blocks trades, never freezes accounts. It surfaces alerts. Decision and execution remain human-overseen per EU AI Act Art 14.

## Honesty Rule conformance

- **Rule 1.** Every `BreachAlert` carries severity + limit_id + limit_type + scope + observed_kes + threshold_kes + utilization_pct + factor + suggested_action + escalation_target + framework_refs + deterministic alert_id. Every `RiskLimit` carries threshold + scope + approval_authority + effective_date + framework_refs.
- **Rule 7.** `LimitMonitor` is purely diagnostic — produces alerts, never executes remediation. Action workflows happen via `treasury_agents` or human approval. Limits are immutable once registered (deactivate + re-register pattern preserves audit history).
- **Decimal-internal precision** throughout — every monetary field is `Decimal`, every percentage is `Decimal` quantized to 2 dp.

## Phase 2 progress after v10.40

| Arc | Status | Standards |
|---|---|---|
| 9 closed arcs | ✅ closed | 91 active |
| Cross-arc scenario harness (v10.36) | ✅ infra | 29 scenarios |
| Cross-arc structural hygiene (v10.38) | ✅ infra | G128 baseline locked, STABLE |
| **Risk arc — Market Risk Foundation (v10.39) + Limits & Breach (v10.40)** | 🟡 **OPEN** | **7 active** |
| Trading book boundary · Credit · Op risk · Liquidity stress | pending | 0 active |

**122 consecutive clean batches.** Risk arc has both measurement (VaR / ES / sensitivities / backtests) AND operational layer (limits / breach detection / escalation). Next likely:

- **v10.41 Trading Book Boundary** — BCBS d352 §A.4 instrument classification (TB vs BB), trading desk concept, FRTB regulatory reporting hooks.
- **v10.42 Credit Risk Foundation** — PD / LGD / EAD per BCBS d424 IRB, expanding beyond v10.6-10 climate-PD overlay.

Each will continue the pattern: pass G128, add 3-5 scenarios, get an Engine Hub tier, no new circular imports.
