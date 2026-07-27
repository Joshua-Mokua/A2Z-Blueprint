# Bundled Loan Product — design (review before build)

**Requirement:** one application can carry several loan products, each with its own amount,
summing to a total. Client selects "Bundled Loan Product", then adds component loan
products + amounts; the deal's value is their sum.

## Current create path (confirmed)
- `POST /api/pipeline/deals` → `pipeline_deal_create` (utils/api.py)
- payload `PipelineDealCreate` — `model_config = ConfigDict(extra="allow")` (extra fields pass through)
- deal carries `deal_value: float` and `product_type: str`
- **Precedent to mirror:** `is_top_up` → handler sets `deal_value = top_up_amount`. Bundle
  does the same: `bundle_lines` present → `deal_value = sum(line amounts)`.
- **Product-readiness gate:** the handler REJECTS any `product_type` not in the catalogue
  with a process flow + SLA. So "Bundled Loan Product" must be seeded as a real product
  with a flow first, or every bundle create 403s.
- Loan products (from data/products.json): Retail Lending + SME Lending =
  Personal Loans, Mortgage Finance, Asset Finance, Salary Advance, Business Loans,
  LPO Financing, Invoice Discounting, Working Capital OD.

## Model: A — line items within ONE deal (one application, one case, one SLA clock)
Not a parent/child structure. The bundle is richer *content* on a single deal, so the
credit chain, SLA clock, and approvals operate unchanged.

## Backend changes (additive, backward-compatible)
1. `PipelineDealCreate`: add
   `bundle_lines: Optional[list[BundleLine]] = None` where
   `BundleLine = {product_type: str, amount: float}`.
2. `pipeline_deal_create` handler, right beside the `is_top_up` block:
   ```
   if deal_dict.get("bundle_lines"):
       lines = [l for l in deal_dict["bundle_lines"] if float(l.get("amount") or 0) > 0]
       if not lines:
           reject("A bundled loan needs at least one product line with an amount.")
       deal_dict["deal_value"]   = round(sum(float(l["amount"]) for l in lines), 2)
       deal_dict["product_type"] = "Bundled Loan Product"
       deal_dict["bundle_lines"] = lines            # persisted on the deal
   ```
3. Seed "Bundled Loan Product" into the catalogue WITH a process flow + SLA
   (reuse the standard loan flow) so the readiness gate passes.
4. Validation: each line's product_type must be a real loan product; amount > 0.

## Frontend changes (create form only, this phase)
- Product picker gains "Bundled Loan Product".
- Selecting it hides the single deal-value field and reveals repeatable rows:
  `[ loan product ▾ ] [ amount ]  (+ Add product) (remove)`
- A live **Total** sums the amounts (read-only) → sent as the basis for deal_value.
- Non-bundle deals: form and payload unchanged.

## Explicitly OUT of scope this phase (documented follow-ons)
- Surfacing the line breakdown in the credit/LMS/committee views (phase 2).
- Per-line tenor/rate/purpose (phase 3 — this phase is product + amount, deal-level terms shared).
- Per-line disbursement (LMS still disburses the one application).

## Decisions for Josh
1. "Bundled Loan Product" as a distinct product_type the user picks first — confirmed?
2. Line = product + amount only for now — confirmed?
3. Bundle follows ONE process flow (the standard loan flow), not per-line flows — confirmed?
