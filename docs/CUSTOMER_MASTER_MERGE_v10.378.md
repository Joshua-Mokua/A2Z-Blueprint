# Customer Master Merge — Design Document

**Version anchor:** v10.378 (May 2026)
**Per:** Joshua's "merge into 1" approval at v10.374 wrap-up
**Companion to:** `A2Z_GOVERNANCE_CONSTITUTION_INTERNAL_v10.377.md`

> "I want us to have eliminate ambiguities, let's have a system operating as one... all the system and organs all functioning perfectly and in harmony to make the one body as a whole."

---

## Part 1 — The two customer universes (today)

### 1.1 CBS `customers.csv` (transactions master)

- **Size**: 100 in seed, 700K in production
- **CIF format**: 10-digit numeric (`1000000001`)
- **Schema**: `cif, full_name, segment, branch_code, rm_code`
- **Authority**: CBS-derived; all accounts/balances/transactions tie here
- **Trust**: 100% — it's the system of record (Oracle FLEXCUBE §3.2)

### 1.2 `customer_intelligence.json` (marketing master)

- **Size**: 3,000 individuals + 206 businesses = **3,206 total**
- **CIF format**:
  - Individuals: 9-digit numeric (`100625608`)
  - Businesses: `CIF<digits>` (`CIF841036`)
- **Schema** (rich): `cif, customer_type, segment, segment_code, clv_estimate, churn_risk, nba, nps_score, digital_engagement, products_held, propensity_scores, tags, complaints_12m, last_contact_days`
- **Authority**: marketing analytics
- **Trust**: high for intelligence attributes; weaker for transactional fields

### 1.3 The problem

Today's pages and modules can read either or both. Different consumers see different customer universes. The MD's "Is the bank on track?" question gets different customer-count answers depending on which file you ask. Modules duplicate logic to handle "is this customer in CBS only" vs "in marketing only" vs "both".

---

## Part 2 — The merge strategy

### 2.1 Atomic unit

**The Unified Customer Record** — one record per distinct customer across all sources. Per the v10.370 atomic-unit pattern:
- Customer is the atom for customer-level analytics
- All downstream consumers (CRM, customer 360, segmentation, profitability) consume the unified record
- The merge engine is the single source of truth for "who is a customer"

### 2.2 Identity matching

For v10.378: **match strictly by CIF**.

| Source CIF format | Treatment |
|---|---|
| CBS `1000000001` (10-digit) | Lookup in marketing as-is |
| Marketing `100625608` (9-digit individual) | Lookup in CBS as-is |
| Marketing `CIF841036` (business) | Lookup in CBS as-is |

CIFs that match → `enrichment_status="both"` (full record).
CIFs only in CBS → `enrichment_status="cbs_only"` (transactional fields populated, intelligence fields None).
CIFs only in marketing → `enrichment_status="marketing_only"` (intelligence fields populated, transactional fields None).

**Fuzzy matching (by name + phone + national_id) is OUT OF SCOPE for v10.378.** That's a real-world data-quality concern that needs its own batch — likely v10.4XX after the canonical layer is established.

### 2.3 Conflict resolution rules

When both sources have a value for the same field:

| Field | Winner | Rationale |
|---|---|---|
| `cif` | Either (must match) | Identity key |
| `full_name` | **CBS** | KYC-authoritative; FLEXCUBE is the legal record |
| `segment` | **CBS** | Today's branch operations use CBS segment |
| `branch_code` | **CBS** | CBS only |
| `rm_code` | **CBS** | CBS only |
| `customer_type` | **Marketing** | Marketing tracks individual/business distinction explicitly |
| `clv_estimate` | Marketing only | CBS doesn't compute it |
| `churn_risk` | Marketing only | CBS doesn't compute it |
| `nba` | Marketing only | Next-best-action from analytics |
| `nps_score` | Marketing only | Survey data |
| `propensity_scores` | Marketing only | Behavioral model output |
| `tags` | Marketing only | Marketing-curated |
| `digital_engagement` | Marketing only | Behavioral analytics |
| `products_held` | **CBS-derived** when v10.378 ships | CBS accounts.csv ground truth; marketing is approximate |
| `complaints_12m` | Marketing only | Complaint system feeds marketing |
| `last_contact_days` | Marketing only | CRM analytic |

The unified record carries `_lineage` showing which source contributed each field.

### 2.4 Reconciliation identity

**Σ(unified records) = | CIFs_CBS ∪ CIFs_marketing |**

Every distinct CIF is represented exactly once. Verifiable invariant:

```
count(unified records)
  = count(distinct CIFs in CBS customers.csv)
  + count(distinct CIFs in customer_intelligence.json + ..._business.json)
  - count(CIFs appearing in both)
```

Locked by G264.

### 2.5 Backward compatibility (Pattern preserved from v10.372)

Both source files **remain untouched** during v10.378. The canonical engine READS them; it does NOT MODIFY them. Existing consumers that read `customer_intelligence.json` directly continue to work. Future batches migrate consumers to the canonical engine; eventually the source files become read-only legacy.

Phase F (PostgreSQL migration) is when source files retire. Until then: dual-source read; canonical merge layer; in-memory unified records.

### 2.6 Storage policy (per constitution §4.3)

**No new JSON files for performance data.** The unified records exist:
- In-memory at engine call time
- Cacheable for short windows (Streamlit `@st.cache_data`)
- Streamable to consumers via Python API

The "single customer master file" approach (writing to `data/customer_master.json`) is REJECTED for v10.378 because:
1. Constitution deprecates new JSON
2. A persisted unified file becomes a 4th customer source (cbs.csv + customer_intelligence + customer_intelligence_business + customer_master) — worse, not better
3. The canonical engine IS the source of truth; it computes the unified view from the authoritative inputs every call

When PostgreSQL arrives, the canonical engine becomes a Postgres view (`SELECT … FROM customers UNION … FROM marketing_intelligence`); the API doesn't change.

---

## Part 3 — Module API

```python
@dataclass
class UnifiedCustomerRecord:
    cif: str
    full_name: Optional[str]
    customer_type: str           # 'individual' | 'business' | 'unknown'
    enrichment_status: str       # 'cbs_only' | 'marketing_only' | 'both'
    # Transactional fields (CBS)
    segment: Optional[str]
    branch_code: Optional[str]
    rm_code: Optional[str]
    # Intelligence fields (Marketing)
    clv_estimate: Optional[float]
    churn_risk: Optional[float]
    nba: Optional[str]
    nps_score: Optional[int]
    digital_engagement: Optional[str]
    products_held: Optional[int]
    propensity_scores: Dict[str, float]
    tags: List[str]
    complaints_12m: Optional[int]
    last_contact_days: Optional[int]
    # Lineage
    sources: List[str]           # ['cbs', 'marketing']
    _field_lineage: Dict[str, str]  # field_name → 'cbs' | 'marketing' | 'derived'

def compute_unified_customer_master(
    cbs_dir: Optional[Path] = None,
) -> Dict[str, UnifiedCustomerRecord]:
    """Return CIF → unified record. Reads both source files; merges per rules."""

def reconciliation_summary(unified: Dict[str, UnifiedCustomerRecord]) -> Dict[str, Any]:
    """Counts by enrichment_status; verifies identity equation; flags anomalies."""

def get_customer(cif: str, cbs_dir: Optional[Path] = None) -> Optional[UnifiedCustomerRecord]:
    """Single-customer lookup via the canonical engine."""
```

---

## Part 4 — Reconciliation identity (G264 lock)

The G264 audit gate verifies on every audit run:

1. **Coverage**: every CIF from both source files appears in the unified output exactly once
2. **Identity equation holds**: `count(unified) == count(distinct CBS CIFs) + count(distinct marketing CIFs) - count(overlap)`
3. **Lineage tagged**: every field in every unified record has a `_field_lineage` entry pointing to its source
4. **Read-only invariant**: the canonical engine module does NOT mutate source files (AST-verified — no `open(..., 'w')` on source paths)
5. **Status totals add up**: `count('cbs_only') + count('marketing_only') + count('both') == count(unified)`

---

## Part 5 — What v10.378 deliberately does NOT do

- Does NOT modify `customer_intelligence.json` or `customers.csv`
- Does NOT write a `data/customer_master.json` file (constitution §4.3)
- Does NOT do fuzzy matching (name/phone) — strict CIF match only
- Does NOT migrate existing pages to consume the unified engine (deferred batches)
- Does NOT compute customer-level PBT — that's `customer_pbt_allocator` (v10.370 atomic)
- Does NOT introduce a new universal record type — `UnifiedCustomerRecord` is for customer master only, distinct from the BSC `UniversalBSCRecord` (which is staff-keyed)
- Does NOT touch `customer_profitability.py` (legacy parallel engine) — that's v10.381

Single concern: **the merge engine + reconciliation identity + audit gate**.

---

## Part 6 — Where customer master fits in the body-system framing

Joshua's framing extended:

| Body system | Banking analog | Layer |
|---|---|---|
| Skeleton (seniority) | Role hierarchy | org_hierarchy_config |
| Circulatory (profitability) | PBT flow | v10.368-v10.375 |
| Nervous (KPI flow) | Universal BSC contract | v10.377 |
| **Recognition / sensory** (customer identity) | **Who is the customer** | **v10.378 NEW** |
| Endocrine (audit) | Reconciliation + audit gates | G1-G264 |
| Brain (governance) | Constitution | v10.377 doc |

The customer master is how the body **recognizes** its customers — the sensory layer that distinguishes one customer from another. Without it, every module sees different shadows of the same customer.

---

## Part 7 — Honest acknowledgement

1. **Strict CIF matching is the v10.378 limitation.** Real-world banks have CIF drift (one customer with multiple CIFs from past migrations). Production deployment needs fuzzy matching. That's v10.4XX.

2. **The seed bank and marketing master are disjoint by design** (different CIF schemes). v10.378's reconciliation will show 100% disjoint on the seed bank — that's correct. Production will show meaningful overlap.

3. **Conflict resolution rules are administrator-overridable.** The defaults in this doc are reasonable; specific banks may want different rules (e.g., name-from-marketing for some legal reason). Not parameterized in v10.378 — future enhancement.

4. **`products_held` is a special case.** Marketing tracks it as an integer (4 products); CBS accounts.csv is the ground truth. In v10.378, we default to marketing's number when available; v10.379+ will derive products_held from CBS accounts.csv directly.

5. **The reconciliation identity is mathematical**: `|A ∪ B| = |A| + |B| - |A ∩ B|`. Verifiable on every run. G264 enforces it.
