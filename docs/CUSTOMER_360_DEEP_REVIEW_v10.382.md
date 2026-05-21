# Customer 360 — Deep Review

**Version anchor:** v10.382 (May 2026)
**Per:** Joshua's directive — *"before you completely close on the customer you could consider a deep review of what is on the customer 360 which might help us"*
**Lens:** Body-system framing — the customer-recognition organ working fully with the rest of the body

Before moving from customer profitability (v10.381) to RM profitability (v10.383), pause to fully understand the Customer 360 organ. What's already on it. What's missing. Where it integrates. What could help.

---

## Part 1 — What's on the page today

**File:** `pages/34_customer360.py` — **3,314 lines** (one of the larger pages)
**Top-level navigation:** 7 tabs

### 1.1 Tab inventory

| # | Tab | What it shows | Sub-tabs |
|---|---|---|---|
| 1 | 🔍 **Customer Lookup** | Search by CIF or name → customer profile (segment, tags, propensity scores, NBA, churn, CLV) | none |
| 2 | 📊 **Portfolio Intelligence** | Aggregate dashboards across the marketing-intel universe | none |
| 3 | ⚠️ **Churn Risk** | Churn scoring per customer, retention priority list, engine reference | 3 sub-tabs (Score Engine, Retention Priority, Engine Reference) |
| 4 | 💡 **Next Best Action** | Per-customer NBA recommendations (cross-sell, retention, etc.) | none |
| 5 | 📈 **Segment Analytics** | RFM analysis, value tier, lifecycle stage, card usage, customer value composite | 5+ sub-tabs |
| 6 | 💰 **Customer Lifetime Value** | CLV computation with cost allocation, holdings, CLV-depth analysis | 3+ sub-tabs |
| 7 | 📄 **IFRS 7 / IAS 24 Disclosures** | Regulatory disclosure views | 2 sub-tabs (IFRS 7, IAS 24) |

### 1.2 Data sources today

```
pages/34_customer360.py
    │
    ├── data/customer_intelligence.json      (3,000 individuals — direct read via _load())
    ├── data/customer_intelligence_business.json (206 businesses — direct read)
    ├── utils/db.py:db (some DB lookups)
    └── utils/customer_profitability.py      (for CLV/PnL computation)
```

**Does NOT yet consume** `compute_unified_customer_master()` from v10.378. It's the largest CONSUMER page that's still on the legacy data path.

---

## Part 2 — What's strong about Customer 360 today

### 2.1 Substantive depth
- **Churn engine** with retention priority scoring (Standard #58)
- **CLV computation** with depth analysis (3+ sub-tabs)
- **RFM analysis** with value tier and lifecycle stage classification (Standard #65)
- **Card Usage Profile** (Standard L05)
- **Customer Value Composite (CVS)** — multi-dimensional scoring (v6.0 / v7.8)
- **IFRS 7 and IAS 24 disclosures** — regulatory-grade reporting

### 2.2 Sophistication
- 3,314 lines is substantial — this isn't a simple lookup page. It's an analytical workbench.
- Multiple Standards integrated (#58, #65, etc.)
- Cost-allocation analysis at customer level
- Engine reference tabs for traceability (per constitution §8.1)

### 2.3 What this organ already does well
The customer-recognition organ has **mature analytics layered on top of recognition**. The bank doesn't just recognize customers — it scores them, ranks them, predicts their churn, identifies their next best action, and computes their lifetime value.

---

## Part 3 — What's missing / fragmented (the gaps)

### 3.1 Not consuming canonical master (v10.378 disconnection)

**The biggest gap.** Customer 360 reads `customer_intelligence.json` directly. It can't see:
- Customers in CBS but not in marketing intel (CBS-only customers — currently invisible to the page)
- The CBS-authoritative fields (segment, branch_code, rm_code) for customers in BOTH
- Provenance/lineage (`_field_lineage`) — when the page shows "segment: Mass", it can't say where that came from

**Consequence:** A CBS account opened yesterday won't appear in Customer 360 until marketing intel updates. The customer-recognition organ has a memory delay.

### 3.2 No PBT view per customer (v10.378→v10.381 disconnection)

Customer 360 has CLV (Customer Lifetime Value — forward-looking projection) but NOT the canonical **Customer PBT** that v10.370/v10.376 already computes. The MD's BSC has customer PBT in canonical form; the Customer 360 page that's literally about customers doesn't surface it.

**Missing organ link:** PBT_BY_CUSTOMER engine output is not consumed by the customer view. The page has the parts to compute PBT (`customer_profitability.py`) but uses it for CLV, not for the canonical PBT contribution to bank PBT.

### 3.3 No segment cross-reference

When the page shows "segment: Mass", it's reading the marketing-intel segment. The CBS-authoritative segment (from CIF KYC) may differ. v10.378 unified master tracks the conflict but Customer 360 doesn't surface it.

### 3.4 No BSC integration

If a customer's churn score crosses a threshold, the bank's BSC should reflect it (Customer Focus pillar — e.g. via NPS or retention KPIs). Customer 360 churn engine produces scores; BSC engine doesn't consume them.

### 3.5 No staff/RM context

Each customer has an `rm_code` in CBS, identifying the relationship manager. Customer 360 shows customer data but doesn't surface "this customer's RM is Mary at Branch BR005, who has 47 other customers averaging KES X PBT." The RM-customer-branch triangle is invisible.

### 3.6 No campaign linkage

`data/card_management.json`, `pages/94_campaigns_management.py` and Customer 360 are separate worlds. A customer with active campaigns isn't flagged in Customer 360.

### 3.7 No Pipeline linkage

If a customer is in the CRM pipeline (page 3_pipeline.py), Customer 360 doesn't surface "this customer has an open deal worth KES X." The customer view shows historic; the pipeline view shows future; they don't meet.

---

## Part 4 — What could help us (the integration opportunities)

### 4.1 Migrate Customer 360 to v10.378 canonical engine (v10.385+ candidate)

Same pattern as v10.381 customer_profitability.py refactor. Replace `_load("customer_intelligence.json")` with `compute_unified_customer_master(cbs_dir=...)`. The page sees:
- CBS-only customers (previously invisible)
- Provenance per field
- Conflict surfacing

**Cost:** Medium (3,314 lines, multiple data paths)
**Benefit:** Customer 360 becomes truly 360 — sees BOTH transactional and analytical truth

### 4.2 Add a "Customer PBT" panel to Customer Lookup tab (v10.386+ candidate)

When user looks up customer X, show:
- Their PBT for the period (from canonical `compute_pbt_by_customer`)
- Their contribution to bank PBT (% of total)
- Their RM's name + branch
- The customer's BSC-cascaded targets (if any — top-100 customers have direct targets)

This makes the customer view rich with canonical numbers, not just marketing predictions.

### 4.3 Cross-link the four organ-systems (v10.387+ candidate)

The customer-recognition organ should display the views from the other organs:

| Other organ | Cross-link in Customer 360 |
|---|---|
| Circulatory (PBT) | This customer's PBT contribution |
| Pipeline (deals) | This customer's open deals |
| Campaigns | This customer's active campaigns |
| RM (staff) | This customer's RM + branch context |
| BSC (KPIs) | This customer's contribution to NPS, CLV-growth KPIs |

Each cross-link is a small panel; collectively they make the customer view comprehensive.

### 4.4 Reconciliation strip (per constitution §5.5)

Top of every tab: tiny strip showing "Σ all customer PBT = bank PBT within tolerance". This puts the canonical accounting in front of the user every time they open the page — same pattern as v10.375 Staff PBT page reconciliation strip.

### 4.5 Customer master view (already prepared by v10.378)

Add an admin/audit tab: "Customer Master" — show the union of CBS + marketing intel as v10.378 produces. Surface customer counts (currently 100 CBS-only + 3,206 marketing-only). Let admin compare populations.

### 4.6 Surface unresolved CIFs

If a CIF is in marketing but not in CBS, surface it explicitly: "This customer has marketing intelligence but no CBS record — possible KYC gap." This is a data-quality control that v10.378's `enrichment_status="marketing_only"` enables.

---

## Part 5 — Implementation order recommendation

Given Customer 360 is already substantial, refactoring it is high-risk-high-reward. Suggested order:

| Step | Batch | Action |
|---|---|---|
| **A** | v10.383 (next per Phase B) | Refactor `rm_profitability.py` to canonical — completes the parallel-engines arc started by v10.381 |
| **B** | v10.384 | Add a NEW tab to Customer 360: "Canonical View" — preview ONLY, using `compute_unified_customer_master`. Doesn't touch existing 7 tabs. |
| **C** | v10.385 | Migrate **Tab 1 (Customer Lookup)** to canonical — smallest tab, lowest risk |
| **D** | v10.386 | Add Customer PBT panel + RM context cross-link |
| **E** | v10.387 | Migrate remaining tabs progressively |
| **F** | v10.388 | Add reconciliation strip |
| **G** | v10.390 | Remove "Canonical View" preview tab (now redundant — all tabs use it) |

This avoids the failure mode of a single big-bang refactor on a 3,314-line page.

---

## Part 6 — Body-system framing

The customer-recognition organ today is **mature but isolated**. It has rich analytics (churn engine, CLV, RFM, CVS) but doesn't fully participate in the body's circulation.

After the suggested integration:
- It sees the customer's PBT contribution → circulatory connection
- It sees the customer's pipeline + campaigns → forward-looking nervous system connection
- It sees the customer's RM and branch → skeleton/staff connection
- It reconciles to bank totals → endocrine (audit) connection

**One body, recognition organ fully wired.**

---

## Part 7 — What v10.382 deliberately does NOT do

This is a review document, not a code change. v10.382 explicitly:

- Does NOT modify Customer 360 page
- Does NOT refactor anything in `pages/34_customer360.py`
- Does NOT propose a single big-bang migration
- Does NOT change data files
- Does NOT touch the existing 7 tabs

The reviews surface the architecture; subsequent batches act on it under Joshua's approval.

---

## Part 8 — Joshua decisions queued from this review

| # | Question |
|---|---|
| C1 | Do you want Customer 360 to consume v10.378 canonical master? (Yes/No/Phased) |
| C2 | Should Customer PBT (canonical) be surfaced on Customer Lookup tab? |
| C3 | Add cross-organ links (Pipeline, Campaigns, RM, BSC)? |
| C4 | Add reconciliation strip? |
| C5 | Add "Customer Master" admin view (CBS-only vs marketing-only counts)? |
| C6 | Refactor order — start with Tab 1 (Customer Lookup) as the canary? |
| C7 | Keep CLV (forward-looking) alongside PBT (backward-looking) or unify? |
