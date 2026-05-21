# CHANGELOG v10.1 — Standards Framework + Regulatory Tier 1 (CBK Prudential)

**Audit:** 118/118 PASS — **85th consecutive clean.**

## What

Opens the v10.x main track (122 → 400 standards expansion). Ships:

### `utils/standards_registry.py` (~360 lines)

First-class standards registry parallel to `utils/system_invariants.py`:
- `Standard` dataclass with 13 fields (id, category, name, source, threshold + direction + unit, affected_engines/pages, audit_gate_id, status, severity, notes)
- 10 categories: engine / regulatory / technical / operational / architectural / kpi / data / test / process / documentation
- 8 regulatory subcategories: CBK / Basel / IFRS / IAS / DPA / KYC-AML / sanctions / FATCA-CRS
- Public API: `list_standards()`, `get_standard()`, `standards_summary()`, `self_test()`

### CBK Prudential Tier 1 (12 standards)

| ID | Name | Threshold | Severity |
|---|---|---|---|
| CBK-PG-01-CAR-CET1 | CET1 ratio | min 10.5% | CRITICAL |
| CBK-PG-01-CAR-TOTAL | Total Capital ratio | min 14.5% | CRITICAL |
| CBK-PG-02-LEVERAGE | Leverage ratio | min 4.5% | HIGH |
| CBK-PG-05-LCR | Liquidity Coverage Ratio | min 100% | CRITICAL |
| CBK-PG-05-NSFR | Net Stable Funding Ratio | min 100% | HIGH |
| CBK-PG-04-SBL | Single Borrower Limit | max 25% | CRITICAL |
| CBK-PG-04-INSIDER | Insider Lending Limit | max 100% | HIGH |
| CBK-PG-08-DORMANCY | Dormant Account Classification | min 24 months | MEDIUM |
| CBK-PG-09-CONSUMER-PROTECTION | Disclosure | (qualitative) | HIGH |
| CBK-PG-09-COMPLAINT-RESOLUTION | Complaint SLA | max 30 days | HIGH |
| CBK-PG-15-RISK-CLASS | 5-tier loan risk classification | (qualitative) | CRITICAL |
| CBK-PG-15-PROVISIONING | Loan loss provisioning rates | (qualitative) | CRITICAL |

Severity distribution: 6 CRITICAL, 5 HIGH, 1 MEDIUM.

### `📐 Standards Hub` admin sub-tab

System section now 7 sub-tabs (G4 cap reached):
- 4 metric tiles (registered / target / progress % / categories defined)
- By-category breakdown
- Active standards detail table (12 standards, 8 columns)
- Severity distribution
- Audit gate coverage
- v10.x roadmap (122→400 expansion)

### Integration tests (10 new tests in `tests/integration/test_standards_registry.py`)

Per Master Prompt v9.29 addendum (every new module needs ≥1 integration test):
- Registry imports cleanly
- v10.1 minimum 12 standards
- All standards have required fields
- Standard IDs unique
- Affected engines exist in utils/
- Threshold consistency (unit + direction)
- list_standards by category / engine
- get_standard / unknown returns None

All passing.

## Coverage progression

| Metric | Pre-v10.0 | v10.1 | v10.5 target |
|---|---|---|---|
| Total standards | 122 | **134** (+12) | 182 |
| Engines | 122 | 122 | 122 |
| Regulatory standards | 0 | **12** (CBK Tier 1) | 60 (full reg tier) |
| Categories defined | 0 | **10** | 10 |
| Audit gates | 118 | 118 | 119 (G119 in v10.5) |

## v10.x first sub-arc plan (v10.1-v10.5)

| Batch | Theme | Standards added |
|---|---|---|
| **v10.1** ✅ | **Tier 1 — CBK Prudential** | **12** |
| v10.2 | Tier 2 — Basel III | 12 |
| v10.3 | Tier 3 — IFRS / IAS | 15 |
| v10.4 | Tier 4 — DPA / KYC / AML / Sanctions | 15 |
| v10.5 | G119 audit gate `regulatory_standards_registered` + arc closure | 0 |

After v10.5: 60 regulatory standards registered. 16-gate defense-in-depth perimeter.

## Honest acknowledgements

1. **CBK threshold values may be updated** — verify with bank compliance team for current applicable values (notes field captures this).
2. **Standards reference engines but don't enforce them at runtime** — registry is descriptive metadata; actual breach detection lives in the affected engines (capital_adequacy, liquidity_risk, etc.).
3. **Affected_pages field uses page filename stem** — `pages/4_capital.py` → `4_capital`. Could be more robust to module path changes.
4. **No standards-vs-engines reconciliation yet** — v10.5 G119 will start enforcing that referenced engines exist; deeper enforcement (engine actually implements the threshold check) is v10.x candidate.
5. **Threshold values stored as Decimal** — not enforced at runtime; engines may use `float` or `Decimal` independently. Consistency check candidate for v10.x.
6. **Subcategory metadata defined but not yet used** — REGULATORY_SUBCATEGORIES tuple is reference; standards don't yet have a `subcategory` field. Future v10.x candidate if needed for finer-grained queries.
7. **Tier 1 covers CBK only** — Basel III is technically also CBK-aligned but separated for v10.2.

## Companion artifact at v10.1

- `utils/standards_registry.py` — registry implementation
- `tests/integration/test_standards_registry.py` — 10 tests
- `pages/7_admin.py` Standards Hub sub-tab — operator surface

## Next: v10.2

Basel III Tier — 12 standards: capital structure (CET1/AT1/Tier 2 separately), counter-cyclical buffer, leverage with total exposure, LCR + NSFR refinement, Pillar 1/2/3 disclosures, total loss-absorbing capacity. Register against the same `STANDARDS_REGISTRY` tuple.
