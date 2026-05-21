# CHANGELOG v9.21 — Engine Integration Hub: Tier 1 (Regulatory + Financial Reporting)

**Audit:** 116/116 PASS — **74th consecutive clean.**

## What

Opens the v9.21-v9.25 Engine Integration Hub arc closing the integration gap (62 engines without UI surfaces → 0 by v9.25). v9.21 ships the Hub framework + first 12 Tier 1 engines.

## Honest snapshot of the integration gap

The 116/70 figures carried in CHANGELOGs were stale. Verified actual:

| Metric | Carried (stale) | Verified (v9.20) | After v9.21 |
|---|---|---|---|
| Engines (utils/) | 116 | **122** | 122 |
| Integrated (imported by pages/) | 70 | **60** | **69** |
| Unintegrated | 46 | **62** | **53** |

Net +9 from v9.21. The hub surfaces 12 engines but 3 were already imported elsewhere — counter increments only by net-new.

## What ships

### New "🔌 Engine Hub" sub-tab in admin System section

System section grew 5 → 6 sub-tabs (G4 cap is 7; remaining = 1).

### Tier 1 engines surfaced (12)

| # | Engine | Purpose |
|---|---|---|
| 1 | `board_reporting` (BoardReportingEngine) | Board-pack consolidation: KPIs + compliance + risk |
| 2 | `earnings_per_share` (EarningsPerShareEngine) | IAS 33 basic + diluted EPS |
| 3 | `cash_flow_statement` (CashFlowEngine) | IAS 7 statement of cash flows |
| 4 | `pillar3_disclosure` | Basel III Pillar 3 disclosures |
| 5 | `regulatory_reporting` | Generic regulatory reporting (CBK BSD returns) |
| 6 | `risk_weighted_assets` | Basel III RWA computation |
| 7 | `market_risk` | VaR + sensitivities + FX exposure |
| 8 | `esg_reporting` (EsgReportingEngine) | GHG inventory + social + governance |
| 9 | `fair_value_measurement` (FairValueEngine) | IFRS 13 fair value hierarchy |
| 10 | `ias1_presentation` (IAS1PresentationEngine) | IAS 1 financial statement presentation |
| 11 | `ias8_policies` (IAS8PoliciesEngine) | IAS 8 changes/errors disclosure |
| 12 | `ifrs7_disclosures` (IFRS7DisclosureEngine) | IFRS 7 financial-instrument disclosures |

### Hub UI surface per engine

Each engine shows in a dataframe row:
- ✓/✗ Importable status
- Expected class presence indicator (e.g. ✓ BoardReportingEngine)
- Public method count (excludes imported types like Dict, Any, List)
- Source line count
- Description

Plus 4 metric tiles at panel bottom:
- Total engines
- Integrated count + percentage
- Unintegrated count
- Hub-surfaced this batch (+N indicator)

## Roadmap (v9.21-v9.25)

| Batch | Tier | Engines (planned) | Net add |
|---|---|---|---|
| **v9.21** | Tier 1 — Regulatory & Financial Reporting | 12 | +9 |
| v9.22 | Tier 2 — Customer Intelligence | ~12 | TBD |
| v9.23 | Tier 3 — Profitability Suite | ~10 | TBD |
| v9.24 | Tier 4-5 — Strategy + Operations | ~12 | TBD |
| v9.25 | G117 audit gate + arc closure | — | — |

After v9.25: ~46 engines integrated via Hub; ~5 infrastructure correctly excluded; near-zero unintegrated user-facing engines. Path clear for the **standards expansion (116 → 400)**.

## Honest acknowledgements

1. **Hub is a lightweight surface, not a deep integration.** Each engine shows status + line count + description. Full operator UIs for each engine remain v10.x candidates per individual deepening priority.
2. **Metric counts net new integrations.** v9.21 adds 12 to the hub; only 9 were previously absent from pages/. Other 3 were already imported (e.g., via API endpoints). The hub still provides operator visibility for all 12.
3. **Description text is hardcoded** in the page; future engines/tiers need updates here. Could be moved to a JSON registry for easier maintenance.
4. **No automatic engine discovery** — operator must add new engines to `ENGINE_HUB_TIERS` dict explicitly. Trade-off intentional: explicit tier assignment beats discovery magic for clarity.
5. **`Class` column heuristic is approximate** — checks `hasattr(mod, expected_class)`; engines without expected class show "—". Some engines (pillar3_disclosure, regulatory_reporting, risk_weighted_assets, market_risk) intentionally have None expected_class because they're function-based not class-based.
6. **Public-methods count filters by `__module__`** to exclude type imports — robust but engines with re-exported helpers may undercount.

## Next: v9.22

Tier 2 — Customer Intelligence engines: deposit_intelligence, dormancy_intelligence, lending_intelligence, treasury_intelligence, customer_lifetime_value (already integrated; verify), customer_segmentation (verify), customer_value_segments (verify), churn_prediction (verify), credit_risk_scoring (verify), customer_profitability (verify), and any others surfacing customer-side analytics.
