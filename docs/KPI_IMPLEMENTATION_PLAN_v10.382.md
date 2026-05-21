# KPI Implementation Plan — Class B KPIs from v10.380 Review

**Version anchor:** v10.382 (May 2026)
**Per:** Joshua's directive — *"the recommendations on kpis let us plan their implemantation"*
**Pre-requisite recommendations:** `V10380_DECISIONS_RECOMMENDATIONS_v10.381.md` (Decision 1 — TIERED ADD)

The recommendation was to add 9 new KPIs (Tier 1 + Tier 2) + alias 1 (NEW_CUST) + verify 1 (PAR) + defer 4. This document is the **implementation plan** — concrete steps, data sources, definitions, schedule.

---

## Part 1 — Implementation tiers (reaffirmed from v10.381 doc)

### Tier 1 — MUST ADD (5 KPIs, Tier-1 banking benchmarks)
- `NIM` — Net Interest Margin
- `CIR` — Cost-to-Income Ratio
- `ROE` — Return on Equity
- `NPS` — Net Promoter Score
- `DEP_GROWTH` — Total Deposit Growth

### Tier 2 — SHOULD ADD (4 KPIs, role-specific completeness)
- `DIGITAL_ACT` — Digital Activation Rate
- 5 `LEGAL_*` SLAs (Chief Legal Officer)

### Tier 3 — ALIAS ONLY (1 KPI)
- `NEW_CUST` → `NEW_CUSTOMERS_ACQUIRED` (no new definition; just alias mapping)

### Tier 4 — VERIFY + POSSIBLY RESOLVE (1 KPI)
- `PAR` — library already has it; need to confirm role_kpis reference resolves

### Tier 5 — DEFER (4 KPIs)
- `FEES_COMM`, `ACTIVE_ACCTS`, `TRANSACTIONS` + already-acknowledged

---

## Part 2 — Per-KPI implementation spec

For each KPI to add, the implementation needs FOUR things:

1. **Library entry** — `kpi_library.json::kpis[]` definition (id, name, pillar, weight, unit, direction, source, active, cbk_ref, description)
2. **Data source** — where the actual value comes from (CBS field, management_accounts, etc.)
3. **Cascade target** — bank-level target value + downstream allocation logic
4. **Consumer wiring** — which pages/engines need to be aware (BSC engine accepts automatically; others may need updating)

### 2.1 NIM — Net Interest Margin

| Field | Value |
|---|---|
| `id` | `NIM` |
| `name` | Net Interest Margin |
| `pillar` | Financial |
| `weight` | 0.15 (within Financial pillar) |
| `unit` | % |
| `direction` | higher |
| `cbk_ref` | CBK Bank Supervision Annual Report standard |
| `source` | `management_accounts` (derived) |
| `formula` | `(interest_income − interest_expense) / average_earning_assets × 100` |
| `description` | Net interest income as % of earning assets. Tier-1 banking benchmark of loan book productivity. |

**Data source detail:**
- `interest_income` — from CBS GL accounts (interest accrued on loans)
- `interest_expense` — from CBS GL accounts (interest paid on deposits)
- `average_earning_assets` — average of opening + closing loan book balance over the period

**Cascade structure:**
- Bank target: e.g. 4.5% — set by MD in admin
- Cascades to Director Retail (CASA-heavy book → ~3.8%), Director Commercial (high-yield → ~5.5%)
- Branch Manager level: target reflects their portfolio mix
- Below BM: KPI doesn't cascade (not RM-controllable)

**Implementation steps:**
1. Add to `kpi_library.json::kpis[]` with above spec
2. Add to `kpi_library.json::active_kpis[]`
3. Add to MD/Director/Head/BM `role_kpis` (12 roles)
4. Build `utils/financial_ratios_engine.py::compute_nim(cbs_dir, period)` — leaf module
5. Add to v10.377 unifier so canonical writer (v10.379) flows it to bsc_actuals
6. Add bank-level target to `bank_targets.json`
7. Cascade in target_cascade UI (12_cascade.py)

### 2.2 CIR — Cost-to-Income Ratio

| Field | Value |
|---|---|
| `id` | `CIR` |
| `name` | Cost-to-Income Ratio |
| `pillar` | Financial |
| `weight` | 0.15 |
| `unit` | % |
| `direction` | lower |
| `cbk_ref` | CBK Bank Supervision Annual Report standard |
| `source` | `management_accounts` |
| `formula` | `total_operating_costs / total_operating_income × 100` |
| `description` | Operating efficiency — lower is better. Tier-1 benchmark. Tracks whether income growth outpaces cost growth. |

**Data source detail:**
- `total_operating_costs` — staff + IT + premises + other_opex (already computed in `pbt_computation.py`)
- `total_operating_income` — net interest income + fees + commissions (already computed)

**Cascade structure:**
- Bank target: e.g. 55% (industry-good); current may be 70%+
- Cascades to SBU Chiefs (cost-center heads) but NOT to revenue-focused branches (they don't control cost)
- Branch Operations Manager level (operational costs): cascades
- Branch Manager level: cascades (overall branch CIR)

**Implementation steps:** Similar to NIM. Engine: `financial_ratios_engine.compute_cir`. Reuses `pbt_computation` outputs.

### 2.3 ROE — Return on Equity

| Field | Value |
|---|---|
| `id` | `ROE` |
| `name` | Return on Equity |
| `pillar` | Financial |
| `weight` | 0.10 |
| `unit` | % |
| `direction` | higher |
| `cbk_ref` | CBK Bank Supervision Annual Report standard |
| `source` | `management_accounts` |
| `formula` | `net_income / average_shareholders_equity × 100` |
| `description` | Shareholder return on capital. Defines whether the bank creates or destroys value. |

**Data source detail:**
- `net_income` — PBT minus tax provision (mgmt_accounts.json should have this)
- `average_shareholders_equity` — from balance sheet equity section

**Cascade structure:**
- Bank target only (MD-level KPI) — does NOT cascade below MD
- Sometimes cascaded to Director-of-Strategy/CFO as informational

**Implementation steps:** Engine: `financial_ratios_engine.compute_roe`. **Needs balance sheet equity data** which may need to be added to management accounts.

### 2.4 NPS — Net Promoter Score

| Field | Value |
|---|---|
| `id` | `NPS` |
| `name` | Net Promoter Score |
| `pillar` | Customer Focus |
| `weight` | 0.20 |
| `unit` | score (-100 to +100) |
| `direction` | higher |
| `cbk_ref` | (none — voluntary disclosure) |
| `source` | `customer_intelligence` (existing field `nps_score` per customer) |
| `formula` | `% Promoters (9-10) − % Detractors (0-6)` from survey responses |
| `description` | Customer loyalty/advocacy metric. The proportion of customers likely to recommend the bank. |

**Data source detail:**
- Per-customer `nps_score` already exists in `customer_intelligence.json` (verified — UnifiedCustomerRecord includes `nps_score`)
- Bank-level NPS = aggregate computation over the customer base

**Cascade structure:**
- Bank target: e.g. +30 (good); +50 (excellent)
- Cascades to Director Retail (customer-facing) but not to back-office roles
- Branch level: each branch's customer base's NPS
- RM level: each RM's portfolio NPS

**Implementation steps:** Engine: `customer_focus_engine.compute_nps(cbs_dir, period)` — aggregates customer_intelligence nps_score field. Uses v10.378 unified master.

### 2.5 DEP_GROWTH — Total Deposit Growth

| Field | Value |
|---|---|
| `id` | `DEP_GROWTH` |
| `name` | Total Deposit Growth |
| `pillar` | Financial |
| `weight` | 0.15 |
| `unit` | % |
| `direction` | higher |
| `cbk_ref` | CBK Liquidity reporting |
| `source` | `cbs_deposits` (aggregate) |
| `formula` | `(deposits_eop − deposits_bop) / deposits_bop × 100` |
| `description` | Bank-wide deposit growth. Aggregates RETAIL_MSME_DEPOSIT + COMMERCIAL_DEPOSIT for MD-level view. |

**Data source detail:**
- Computable from existing CBS data — no new source needed
- Aggregates the two existing deposit growth KPIs (Retail & MSME + Commercial)

**Cascade structure:**
- Bank target only (MD-level KPI)
- Doesn't cascade — the sub-KPIs (RETAIL_MSME_DEPOSIT, COMMERCIAL_DEPOSIT) already cascade

**Implementation steps:** Engine: `financial_ratios_engine.compute_total_deposit_growth(cbs_dir, period)`. Aggregates existing computations.

### 2.6 DIGITAL_ACT — Digital Activation Rate

| Field | Value |
|---|---|
| `id` | `DIGITAL_ACT` |
| `name` | Digital Activation Rate |
| `pillar` | Customer Focus |
| `weight` | 0.10 |
| `unit` | % |
| `direction` | higher |
| `cbk_ref` | (none) |
| `source` | `cbs_customers` (digital_engagement field) + customer counts |
| `formula` | `digitally_active_customers / total_customers × 100` |
| `description` | Proportion of customers with at least one digital transaction in the period. Digital banking adoption metric. |

**Implementation steps:** Engine reads UnifiedCustomerRecord `digital_engagement` field (already in v10.378 schema). Threshold for "active" (e.g. ≥1 transaction in 30 days) needs admin configuration.

### 2.7 LEGAL_* — Chief Legal Officer SLAs

| ID | Name | Direction | Description |
|---|---|---|---|
| `LEGAL_OVERDUE_RATE` | Legal Overdue Rate | lower | % of legal matters past their SLA deadline |
| `LEGAL_SLA_ATTORNEY` | Legal SLA — Attorney Engagement | higher | % attorney instructions issued within SLA |
| `LEGAL_SLA_DOCS` | Legal SLA — Document Review | higher | % document reviews completed within SLA |
| `LEGAL_SLA_SECURITY` | Legal SLA — Security/Collateral | higher | % collateral docs perfected within SLA |
| `LEGAL_SLA_VALUATION` | Legal SLA — Property Valuation | higher | % valuations completed within SLA |

All pillar = Process. All unit = %. All weight = 0.20 each (sums to 1.00 across the Legal Officer's 5 SLAs).

**Data source:** Each requires SLA tracking inputs that don't fully exist today. **Implementation requires SLA capture mechanism** — likely page 5_sla_tracker.py extension OR new admin table.

**Implementation steps:**
1. Add 5 library entries
2. Add to Chief Legal Officer's role_kpis
3. Build SLA-event capture (new admin section)
4. Build `legal_sla_engine.compute_legal_slas(period)` — aggregates events
5. Add cascade target (CLO-level only, doesn't cascade)

**This is the most-deferred Tier-2 work — requires new data capture, not just engine.**

---

## Part 3 — New module: `utils/financial_ratios_engine.py`

A single leaf module covers NIM + CIR + ROE + DEP_GROWTH (the four Financial ratio KPIs).

```python
"""utils/financial_ratios_engine.py — v10.383+ Financial Ratio KPIs.

Computes NIM, CIR, ROE, DEP_GROWTH from CBS + management_accounts data.
Leaf module — zero upward imports. Returns DecimalResult.
"""

@dataclass
class NIMResult:
    period: str
    interest_income: Decimal
    interest_expense: Decimal
    avg_earning_assets: Decimal
    nim_pct: Decimal  # the headline

def compute_nim(cbs_dir: Optional[Path], period: str) -> NIMResult: ...
def compute_cir(cbs_dir: Optional[Path], period: str) -> CIRResult: ...
def compute_roe(cbs_dir: Optional[Path], period: str) -> ROEResult: ...
def compute_total_deposit_growth(cbs_dir: Optional[Path], period: str) -> DepGrowthResult: ...
```

Each `compute_*` returns a result dataclass with both the headline number AND the components used (for traceability per constitution §8.1).

---

## Part 4 — New module: `utils/customer_focus_engine.py`

Covers NPS + DIGITAL_ACT — both source from v10.378 unified master.

```python
"""utils/customer_focus_engine.py — v10.383+ Customer Focus KPIs.

Computes NPS, DIGITAL_ACT from unified customer master (v10.378).
Aggregates per-customer scores into bank/SBU/branch/RM dimensions.
"""

def compute_bank_nps(period: str) -> NPSResult: ...
def compute_branch_nps(branch_code: str, period: str) -> NPSResult: ...
def compute_rm_nps(rm_code: str, period: str) -> NPSResult: ...
def compute_digital_activation(cbs_dir, period: str) -> DigitalActResult: ...
```

---

## Part 5 — Cascade target structure

For each new KPI that cascades, the bank target needs to be:
1. Set in `bank_targets.json` at MD level
2. Cascaded by MD through admin UI (page 12_cascade.py) to direct reports
3. Cascaded by each level to their reports

**Target-setting workflow:**
- MD sets bank-level target (e.g. NIM = 4.5%)
- For ratio KPIs (NIM, CIR, ROE): common target — every level inherits the same %
- For aggregate KPIs (DEP_GROWTH): MD's target is the bank total; allocated proportionally to SBU/branch deposit shares
- For score KPIs (NPS): common target — every level should hit the same NPS

---

## Part 6 — Implementation schedule

Suggested batch sequence (assumes Joshua approves Decision 1):

| Batch | Concern | KPIs |
|---|---|---|
| v10.383 | rm_profitability canonical refactor (Phase B commitment) | — |
| v10.384 | Add Financial ratio engines + 4 KPIs | NIM, CIR, ROE, DEP_GROWTH |
| v10.385 | Add Customer Focus engines + 2 KPIs | NPS, DIGITAL_ACT |
| v10.386 | Alias NEW_CUST → NEW_CUSTOMERS_ACQUIRED + verify PAR | — |
| v10.387 | Build legal SLA capture mechanism | (preparation for v10.388) |
| v10.388 | Add 5 LEGAL_* KPIs + Chief Legal Officer BSC wiring | 5 LEGAL_* |
| v10.389 | Bank target setting + initial cascade for all new KPIs | — |
| v10.390 | First end-to-end BSC computation with all new KPIs | — |

After v10.390: MD's BSC presents the full banking story for the first time.

---

## Part 7 — Risks + mitigations

| Risk | Mitigation |
|---|---|
| Management_accounts data may not have all components needed for ROE (shareholders' equity) | Add missing fields explicitly in v10.384; document gaps |
| Bank-level NPS target may be aspirational with no historical data | Set initial target as "improve from baseline" (delta-based) until enough history accumulates |
| Legal SLA capture requires UX/process change | Defer until after Tier-1 ratios land; can be parallel-tracked |
| Adding 9 KPIs increases BSC composite-score complexity | Test composite score remains computable after each batch (G-gate per batch) |
| Existing consumers of `pillar_weights` may need re-test | Smoke test pages 1_perform.py, 12_cascade.py, 7_admin.py after each batch |

---

## Part 8 — Body-system framing

The 9 new KPIs aren't just additional metrics — they're missing sensory organs the body currently lacks.

| KPI | What organ it gives the body |
|---|---|
| NIM | The organ that senses whether the loan book is generating margin |
| CIR | The organ that senses cost-vs-income balance |
| ROE | The organ that senses shareholder-value creation |
| NPS | The organ that senses customer advocacy/loyalty |
| DEP_GROWTH | The organ that senses bank-wide deposit-base momentum |
| DIGITAL_ACT | The organ that senses digital channel adoption |
| 5 LEGAL_* | The organs that sense legal-function operational health |

Without these, the body can't fully sense itself. The MD's BSC currently shows PBT (the heart-rate) but not blood pressure (NIM), oxygen saturation (ROE), or customer pulse (NPS). After implementation, the body has its full vital-signs panel — exactly what constitution §1 charter "Is the bank on track?" requires.

Each engine module is a small, well-defined organ: `financial_ratios_engine` covers the four financial vital signs; `customer_focus_engine` covers the customer-organ sensors. The architecture stays clean: one engine per logical organ, each engine a leaf module.

---

## Part 9 — Joshua decisions queued from this plan

| # | Question |
|---|---|
| K1 | Approve all 9 Tier-1+Tier-2 additions, or only Tier-1? |
| K2 | NIM weight within Financial pillar — 0.15 or different? |
| K3 | ROE — does mgmt_accounts.json have shareholders' equity, or need to add? |
| K4 | NPS bank target — your number? (suggestion: +30) |
| K5 | DIGITAL_ACT — define "active" threshold (≥1 txn in 30 days?) |
| K6 | LEGAL_* — defer SLA capture to v10.387+ as suggested, or accelerate? |
| K7 | Bank-level target values for NIM/CIR/ROE/DEP_GROWTH? |
| K8 | Cascade — common target for ratio KPIs or differentiated by sub-unit? |
